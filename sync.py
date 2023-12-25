import argparse
import os
import re
import sys
import time
import paramiko
import hashlib
from collections import OrderedDict
from paramiko import RSAKey
from scp import SCPClient

# This is the official delimiter character, ASCII code 30... Too bad the industry settled on commas.
# Hopefully this will have less chance of conflicting with filenames.
record_separator = "\u001E"


class Client:
    def __init__(
        self,
        ip,
        ssh_client,
        scp_client,
        source_path,
        destination_path,
        limit_gb,
        port=22,
        username="root",
    ):
        self.ip = ip
        self.port = port
        self.username = username
        self.source_path = source_path
        self.destination_path = destination_path
        self.storage_limit_bytes = limit_gb * (1024**3)

        # initialize to now, but will be overwritten.
        self.oldest_date_at_dest = time.time()

        self.existing_file_metadata = OrderedDict()
        self.size_of_existing_files = 0
        self.source_files = []
        self.size_of_new_files = 0

        self.bad_files = []

        self.ssh = ssh_client
        self.scp = scp_client

    def __del__(self):
        if self.scp:
            self.scp.close()
        if self.ssh:
            self.ssh.close()

    def _ssh_command(self, command):
        _, stdout, stderr = self.ssh.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
        if error:
            print("Error:", file=sys.stderr)
            print(error, file=sys.stderr)
        return output

    def _scp_command(self, source_path, dest_path):
        self.scp.put(source_path, dest_path, preserve_times=True)

    def _scan_source_files(self):
        with os.scandir(self.source_path) as it:
            for entry in it:
                if entry.is_file():
                    size_bytes = entry.stat().st_size
                    modified_date = int(os.path.getmtime(entry.path))
                    filename = entry.name
                    if (
                        modified_date < self.oldest_date_at_dest
                        or filename in self.existing_file_metadata
                    ):
                        continue
                    self.source_files.append((modified_date, filename, size_bytes))
                    self.size_of_new_files += size_bytes

        self.source_files.sort()

    def _scan_destination_files(self):
        command = f"""
        for file in /sdcard/sync/{self.destination_path}/*; do
            echo "$(basename "$file"){record_separator}$(stat -c %Y "$file"){record_separator}$(stat -c %s "$file"){record_separator}$(md5sum -b "$file")"
        done
        """
        output = self._ssh_command(command)
        # splitlines() considers ASCII 30 to be equivalent to newline. (╯°□°)╯︵ ┻━┻
        lines = output.split("\n")
        for line in lines:
            items = line.split(record_separator)
            if len(items) < 4:
                continue
            filename = items[0]
            modified_date = int(items[1])
            size_bytes = int(items[2])
            md5 = items[3]
            # print(f"{modified_date} : {filename} : {size_bytes} : {md5}")
            self.oldest_date_at_dest = min(self.oldest_date_at_dest, modified_date)
            self.existing_file_metadata[filename] = (modified_date, size_bytes, md5)
            self.size_of_existing_files += size_bytes

        self.existing_file_metadata = OrderedDict(
            sorted(self.existing_file_metadata.items(), key=lambda val: val[1][0])
        )

    def _check_integrity(self, source_dir, new_files=None):
        for filename, metadata in self.existing_file_metadata.items():
            path = os.path.join(source_dir, filename)
            md5 = metadata[2].lower()

            # Skip if the file does not exist.
            if not os.path.exists(path):
                continue

            # Open the file in binary mode for md5 calculation
            with open(path, "rb") as f:
                source_content = f.read()
                if hashlib.md5(source_content).hexdigest().lower() != md5:
                    self.bad_files.append(filename)

    def _create_ready_file(self):
        self._ssh_command(f"touch /sdcard/sync/ready_to_scan")

    def _delete_existing_file(self, name):
        self._ssh_command(f"rm /sdcard/sync/{self.destination_path}/{name}")
        size = self.existing_file_metadata[name][1]
        self.size_of_existing_files -= size
        self.existing_file_metadata.pop(name)

    def _make_space(self, amount_bytes):
        if amount_bytes == 0:
            return

        print("Freeing up", amount_bytes, "bytes of space on the phone...")

        current_filenames = list(self.existing_file_metadata.keys())
        for name in current_filenames:
            size = self.existing_file_metadata[name][1]
            print("Deleting from phone:", name)
            self._delete_existing_file(name)
            amount_bytes -= size
            if amount_bytes <= 0:
                return

    def _copy_over_file(self, file_dir, file_name, size=None):
        if size:
            available_space = self.storage_limit_bytes - self.size_of_existing_files
            if available_space < size:
                self._make_space(size - available_space)
        print(
            "Copying",
            file_dir + file_name,
            "to",
            f"/sdcard/sync/{self.destination_path}/{file_name}",
        )
        self._scp_command(
            file_dir + file_name, f"/sdcard/sync/{self.destination_path}/{file_name}"
        )

    def send_new_files(self, source_path):
        # Scan all existing files on phone
        print("Scanning existing files on destination phone...")
        self._scan_destination_files()

        # Scan source files
        print("Scanning files from source directory...")
        self._scan_source_files()
        print("Found", len(self.source_files), "new files.")

        if not self.source_files:
            # There are no new files to copy over.
            return

        # Delete some old files
        available_space = self.storage_limit_bytes - self.size_of_existing_files
        if available_space < self.size_of_new_files:
            print("Making some space.")
            self._make_space(self.size_of_new_files - available_space)

        # Copy over new files
        print("Copying over new files.")
        for _, filename, size_bytes in self.source_files:
            self._copy_over_file(source_path, filename, size_bytes)

        # Scan all existing files on phone
        print("There are new files copied over. Checking the integrity of the files.")
        self._scan_destination_files()

        # Check their integrity with the source files
        self._check_integrity(source_path)
        while self.bad_files:
            print("Found bad files:", self.bad_files)
            print("Copying the bad files over again.")
            # Replace the bad files
            for filename in self.bad_files:
                self._delete_existing_file(filename)
                self.copy_over_files(source_path, filename)

            # Check integrity again
            self.bad_files = []
            print("Checking the integrity of the files again.")
            self._scan_destination_files()
            self._check_integrity(source_path)

        # Write ready file
        self._create_ready_file()

        print("Done!")


def create_client(
    ip, key_path, source_path, destination_path, limit, port=22, username="root"
):
    # Create an SSH client instance
    ssh = paramiko.SSHClient()

    # Automatically add the server's host key (this is insecure in production)
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Load the private key
    private_key = RSAKey.from_private_key_file(key_path)

    # Connect to the server
    ssh.connect(ip, port=port, username=username, pkey=private_key)

    # Setup SCP
    scp = SCPClient(ssh.get_transport())

    return Client(ip, ssh, scp, source_path, destination_path, limit, port, username)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copy new media to the phone and delete older files."
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        type=str,
        help="Path to the directory that contains all of the media files you want to sync.",
    )
    parser.add_argument(
        "--destination",
        "-d",
        required=True,
        type=str,
        help="Directory name on the phone within /sync.",
    )
    parser.add_argument(
        "--phone_ip", "--ip", required=True, type=str, help="IP address of the phone."
    )
    parser.add_argument(
        "--phone_port_num",
        "--port",
        required=True,
        type=int,
        help="Port number that the phone SSH daemon is listening on.",
    )
    parser.add_argument(
        "--rsa_key_path",
        "--rsa",
        type=str,
        default="~/.ssh/id_rsa",
        help="Path to your SSH key.",
    )
    parser.add_argument(
        "--storage_limit_gb",
        "--limit",
        type=int,
        default=10,
        help="Limit in GiBs. Deletes the oldest files from the destination to stay under this limit. Defaults to 10GiB.",
    )
    args = parser.parse_args()

    client = create_client(
        args.phone_ip,
        args.rsa_key_path,
        args.source,
        args.destination,
        args.storage_limit_gb,
        args.phone_port_num,
    )
    client.send_new_files(args.source)

import argparse
import os
import re
import sys
import time
import paramiko
from paramiko import RSAKey
from scp import SCPClient
from queue import PriorityQueue

# This is the official delimiter character, ASCII code 30... Too bad the industry settled on commas.
# Hopefully this will have less chance of conflicting with filenames.
record_separator = '\u001E'


class Client:
    def __init__(self, ip, ssh_client, scp_client, destination_path, limit_gb, port=22, username='root'):
        self.ip = ip
        self.port = port
        self.username = username
        self.destination_path = destination_path
        self.storage_limit_bytes = limit_gb * (1024 ** 3)

        self.oldest_date_at_dest = time.time()  # initialize to now, but will be overwritten.
        self.existing_files_pq = PriorityQueue()
        self.existing_filenames = set()
        self.size_of_existing_files = 0
        self.source_files_pq = PriorityQueue()
        self.size_of_new_files = 0

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
    
    def _scan_source_files(self, source_path):
        with os.scandir(source_path) as it:
            for entry in it:
                if entry.is_file():
                    size_bytes = entry.stat().st_size
                    modified_date = int(os.path.getmtime(entry.path))
                    filename = entry.name
                    if modified_date < self.oldest_date_at_dest or filename in self.existing_filenames:
                        continue
                    self.source_files_pq.put((modified_date, filename, size_bytes))
                    self.size_of_new_files += size_bytes
    
    def _scan_destination_files(self):
        command = f"""
        for file in /sdcard/sync/{self.destination_path}/*; do
            echo "$(basename "$file"){record_separator}$(stat -c %Y "$file"){record_separator}$(stat -c %s "$file")"
        done
        """
        output = self._ssh_command(command)
        lines = output.split('\n')  # splitlines() considers ASCII 30 to be equivalent to newline. (╯°□°)╯︵ ┻━┻
        for line in lines:
            items = line.split(record_separator)
            if len(items) != 3:
                continue
            size_bytes = int(items[2])
            modified_date = int(items[1])
            filename = items[0]
            # print(f"{modified_date} : {filename} : {size_bytes}")
            self.oldest_date_at_dest = min(self.oldest_date_at_dest, modified_date)
            self.existing_files_pq.put((modified_date, filename, size_bytes))
            self.existing_filenames.add(filename)
            self.size_of_existing_files += size_bytes

    def _delete_existing_file(self, name, size):
        self._ssh_command(f'rm /sdcard/sync/{self.destination_path}/{name}')
        self.size_of_existing_files -= size
        self.existing_filenames.remove(name)
    
    def _make_space(self, amount_bytes):
        if amount_bytes == 0:
            return

        print('Freeing up', amount_bytes, 'bytes of space on the phone...')

        while not self.existing_files_pq.empty():
            _, name, size = self.existing_files_pq.get()
            print('Deleting from phone:', name)
            self._delete_existing_file(name, size)
            amount_bytes -= size
            if amount_bytes <= 0:
                return
    
    def _copy_over_file(self, file_dir, file_name, size):
        available_space = self.storage_limit_bytes - self.size_of_existing_files
        if available_space < size:
            self._make_space(size - available_space)
        print('Copying', file_dir + file_name, 'to', f'/sdcard/sync/{self.destination_path}/{file_name}')
        self._scp_command(file_dir + file_name, f'/sdcard/sync/{self.destination_path}/{file_name}')
    
    def send_new_files(self, source_path):
        print('Scanning existing files on destination phone...')
        self._scan_destination_files()
        print('Found', len(self.existing_filenames), 'files.')
        print('Scanning files from source directory...')
        self._scan_source_files(source_path)
        print('Found', self.source_files_pq.qsize(), 'new files.')

        available_space = self.storage_limit_bytes - self.size_of_existing_files
        if available_space < self.size_of_new_files:
            self._make_space(self.size_of_new_files - available_space)
        while not self.source_files_pq.empty():
            _, filename, size_bytes = self.source_files_pq.get()
            self._copy_over_file(source_path, filename, size_bytes)


def create_client(ip, key_path, destination_path, limit, port=22, username='root'):
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

    return Client(ip, ssh, scp, destination_path, limit, port, username)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Copy new media to the phone and delete older files.')
    parser.add_argument('--source', '-s', required=True, type=str, help='Path to the directory that contains all of the media files you want to sync.')
    parser.add_argument('--destination', '-d', required=True, type=str, help='Directory name on the phone within /sync.')
    parser.add_argument('--phone_ip', '--ip', required=True, type=str, help='IP address of the phone.')
    parser.add_argument('--phone_port_num', '--port', required=True, type=int, help='Port number that the phone SSH daemon is listening on.')
    parser.add_argument('--rsa_key_path', '--rsa', type=str, default='~/.ssh/id_rsa', help='Path to your SSH key.')
    parser.add_argument('--storage_limit_gb', '--limit', type=int, default=30, help='Limit in GiBs. Deletes the oldest files from the destination to stay under this limit. Defaults to 30GiB.')
    args = parser.parse_args()

    client = create_client(args.phone_ip, args.rsa_key_path, args.destination, args.storage_limit_gb, args.phone_port_num)
    client.send_new_files(args.source)

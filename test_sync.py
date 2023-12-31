import unittest
from sync import Client, record_separator
from unittest.mock import patch


def read_some_files():
    output = []
    for i in range(10, 0, -1):
        output.append(
            f"{i}{record_separator}{i}{record_separator}{i}{record_separator}{i}"
        )
    return "\n".join(output)


class ClientTestModule(unittest.TestCase):
    def setUp(self):
        self.client = Client("0.0.0.0", None, None, "boo", "foo", 1)

    @patch.object(Client, "_delete_existing_file")
    def test_make_space_empty(self, mock_delete_existing_file):
        self.assertEqual(self.client.size_of_existing_files, 0)
        self.client._make_space(0)
        self.client._make_space(1)
        self.client._make_space(99999999)
        self.assertEqual(self.client.size_of_existing_files, 0)

        mock_delete_existing_file.assert_not_called()

    @patch.object(Client, "_ssh_command")
    def test_make_space(self, mock_ssh_command):
        mock_ssh_command.return_value = read_some_files()
        self.client._scan_destination_files()

        self.client._make_space(0)
        self.assertEqual(len(self.client.existing_file_metadata), 10)
        self.assertEqual(self.client.size_of_existing_files, 55)

        # Deletes the oldest file.
        self.client._make_space(1)
        self.assertEqual(len(self.client.existing_file_metadata), 9)
        self.assertNotIn("1", self.client.existing_file_metadata)
        self.assertEqual(self.client.size_of_existing_files, 54)

        # Previously deleted file is not re-deleted.
        self.client._make_space(1)
        self.assertEqual(len(self.client.existing_file_metadata), 8)
        self.assertNotIn("2", self.client.existing_file_metadata)
        self.assertEqual(self.client.size_of_existing_files, 52)

        # Exactly 3 file's worth of space freed.
        self.client._make_space(3 + 4 + 5)
        self.assertEqual(len(self.client.existing_file_metadata), 5)
        self.assertEqual(self.client.size_of_existing_files, 40)

        # Two file's worth + 1 byte so it would still need to delete a third.
        self.client._make_space(6 + 7 + 1)
        self.assertEqual(len(self.client.existing_file_metadata), 2)
        self.assertEqual(self.client.size_of_existing_files, 19)

        # Exceed remaining files should just delete everything and not error
        self.client._make_space(9999999)
        self.assertEqual(len(self.client.existing_file_metadata), 0)
        self.assertEqual(self.client.size_of_existing_files, 0)

    @patch.object(Client, "_ssh_command")
    def test_delete_file(self, mock_ssh_command):
        mock_ssh_command.return_value = read_some_files()
        self.client._scan_destination_files()

        # Can delete the first file.
        f = 1
        self.client._delete_existing_file(str(f))
        self.assertEqual(len(self.client.existing_file_metadata), 9)
        self.assertNotIn(str(f), self.client.existing_file_metadata)
        self.assertEqual(self.client.size_of_existing_files, 54)

        # Can delete a random file in the middle.
        f = 5
        self.client._delete_existing_file(str(f))
        self.assertEqual(len(self.client.existing_file_metadata), 8)
        self.assertNotIn(str(f), self.client.existing_file_metadata)
        self.assertEqual(self.client.size_of_existing_files, 49)

        self.assertEqual(
            ["2", "3", "4", "6", "7", "8", "9", "10"],
            list(self.client.existing_file_metadata.keys()),
        )

    @patch.object(Client, "_ssh_command")
    def test_scan_destination_files(self, mock_ssh_command):
        mock_ssh_command.return_value = read_some_files()

        self.client._scan_destination_files()
        mock_ssh_command.assert_called_once()
        self.assertEqual(len(self.client.existing_file_metadata), 10)
        self.assertEqual(self.client.size_of_existing_files, 55)

        for i in range(1, 11):
            self.assertIn(str(i), self.client.existing_file_metadata)
            self.assertEqual(self.client.existing_file_metadata[str(i)], (i, i, str(i)))


if __name__ == "__main__":
    unittest.main()

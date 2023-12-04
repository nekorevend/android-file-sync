import unittest
from sync import Client, record_separator
from unittest.mock import patch

def read_some_files():
    output = []
    for i in range(10, 0, -1):
        output.append(f'{i}{record_separator}{i}{record_separator}{i}')
    return '\n'.join(output)

class ClientTestModule(unittest.TestCase):

    def setUp(self):
        self.client = Client('0.0.0.0', None, None, 'foo', 1)

    @patch.object(Client, '_delete_existing_file')
    def test_make_space_empty(self, mock_delete_existing_file):
        self.assertEqual(self.client.size_of_existing_files, 0)
        self.client._make_space(0)
        self.client._make_space(1)
        self.client._make_space(99999999)
        self.assertEqual(self.client.size_of_existing_files, 0)

        mock_delete_existing_file.assert_not_called()

    @patch.object(Client, '_ssh_command')
    def test_make_space(self, mock_ssh_command):
        mock_ssh_command.return_value = read_some_files()
        self.client._scan_destination_files()

        self.client._make_space(0)
        self.assertEqual(len(self.client.existing_filenames), 10)
        self.assertEqual(self.client.size_of_existing_files, 55)

        # Deletes the oldest file.
        self.client._make_space(1)
        self.assertEqual(len(self.client.existing_filenames), 9)
        self.assertTrue('1' not in self.client.existing_filenames)
        self.assertEqual(self.client.size_of_existing_files, 54)

        # Previously deleted file is not re-deleted.
        self.client._make_space(1)
        self.assertEqual(len(self.client.existing_filenames), 8)
        self.assertTrue('2' not in self.client.existing_filenames)
        self.assertEqual(self.client.size_of_existing_files, 52)
        
        # Exactly 3 file's worth of space freed.
        self.client._make_space(3+4+5)
        self.assertEqual(len(self.client.existing_filenames), 5)
        self.assertEqual(self.client.size_of_existing_files, 40)
        
        # Two file's worth + 1 byte so it would still need to delete a third.
        self.client._make_space(6+7+1)
        self.assertEqual(len(self.client.existing_filenames), 2)
        self.assertEqual(self.client.size_of_existing_files, 19)
        
        # Exceed remaining files should just delete everything and not error
        self.client._make_space(9999999)
        self.assertEqual(len(self.client.existing_filenames), 0)
        self.assertEqual(self.client.size_of_existing_files, 0)

    @patch.object(Client, '_ssh_command')
    def test_scan_destination_files(self, mock_ssh_command):
        mock_ssh_command.return_value = read_some_files()

        self.client._scan_destination_files()
        mock_ssh_command.assert_called_once()
        self.assertEqual(len(self.client.existing_filenames), 10)
        self.assertEqual(self.client.size_of_existing_files, 55)

        for i in range(1, 11):
            self.assertEqual(self.client.existing_files_pq.get(), (i, str(i), i))
            self.assertTrue(str(i) in self.client.existing_filenames)

if __name__ == '__main__':
    unittest.main()

# Android File Sync (for Google Photos)
Automatically copy *new* files to an Android phone.

## Motivation
Google Photos stopped providing free unlimited photo backups, but Pixel phones up to the Pixel 5 retain this benefit (and make no distinction about whether the pictures it backs up were taken using that Pixel). So, it is possible to copy your photos over to the Pixel phone for it to back up for free to Google Photos. I wrote this tool to help automate that process.

## Why not rsync?
Rsync is designed to keep two directories in sync. But once Google Photos has backed up the photos, those photos no longer need to be on the phone. While you can, and should, delete the files from the phone after they've been backed up, I was unable to find a way to prevent rsync from copying those files back in.

I made this tool to bridge that gap. It will only copy *new* files to the phone and ignore that old files are missing from the phone.

## How to Install

### On your computer

Every platform is different so these instructions are only in general terms.

1. Download the `sync.py` and `requirements.txt` files.
    - Or install [git](https://git-scm.com/) and `git clone` this repository.
1. Use a [Python virtual environment](https://docs.python.org/3/library/venv.html) with [pip](https://packaging.python.org/en/latest/key_projects/#pip) to set up the dependencies for this tool.

### On your Pixel phone
1. Install [SimpleSSHD](https://www.galexander.org/software/simplesshd/).
    - For the computer to be able to SSH into the phone to copy the files over.
    - Set it up to accept your computer's SSH public key.
1. Install [Tasker](https://tasker.joaoapps.com/).
    - For activating Media Scan. Android will not realize you've copied over any photos until you run a Media Scan on those files.
    - There are alternative apps specifically for doing the Media Scan, but Tasker can allow you to automate this process.
        - I want to set the Pixel phone aside and never need to touch it, so I use Tasker. You can skip Tasker if you are okay manually triggering a scan.
    - TODO - Specific instructions

## How to Use
1. Create a `sync` directory at the root of your phone storage (the directory that contains `DCIM`, `Pictures`, `Movies`, etc.).
1. Within `sync`, create a directory for each source folder you want to sync. For example, if I want to sync photos from a Galaxy and an iPhone and have their photos in separate source folders, then I would create `/sync/galaxy` and `/sync/iphone`.
    - Each directory will be a separate run of this tool.
1. Initialize the directories by copying over the oldest file you want to have synced into each respective directory.
    - The tool will read this file's modified date as the cutoff point and only copy files over that are newer than this file.
    - This file will later be deleted when the sliding window has to make space for newer files.
1. Open the Google Photos app and turn on auto backup of your destination folders (`galaxy` and `iphone` in my example).
1. With SimpleSSHD set up with your computer's SSH public key, let's make the following assumptions for the example command below:
    - Phone IP is `192.168.0.111`.
    - SSH port is `2222` (default with SimpleSSHD).
    - Your SSH key is at `~/.ssh/id_rsa`.
1. An example command is: `python sync.py --source /media/cameras/galaxy/ --destination galaxy --phone_ip 192.168.0.111 --phone_port_num 2222 --rsa ~/.ssh/id_rsa`
    - This will copy any newer files from `/media/cameras/galaxy` on your computer to `/sdcard/sync/galaxy` on your Pixel phone.

## Known limitations
- I did not design this to work recursively, so only files in the provided source directory are considered.
- It requires you to manually initialize with a starting file in the destination directory.
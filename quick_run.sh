#!/bin/bash
source venv/bin/activate
echo p8
python sync.py --source /media/cameras/Pixel\ 8/ --destination p8 --phone_ip 192.168.0.144 --phone_port_num 2222 --rsa /home/vchang/.ssh/id_rsa_photos
echo p8v
python sync.py --source /media/cameras/Pixel\ 8\ Videos/ --destination p8v --phone_ip 192.168.0.144 --phone_port_num 2222 --rsa /home/vchang/.ssh/id_rsa_photos
deactivate
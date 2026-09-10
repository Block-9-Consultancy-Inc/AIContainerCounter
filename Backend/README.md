### Setting up NFC scanner on Fedora 42
1.
```
sudo dnf install -y pcsc-lite pcsc-lite-devel pcsc-tools ccid pcsc-lite-acsccid-0:1.1.11-4.fc42.x86_64
sudo systemctl enable pcscd
sudo systemctl start pcscd
```

2. Blacklist the following modules by adding these lines to /etc/modprobe.d/blacklist.conf
```
install nfc /bin/false
install pn533 /bin/false
install pn533_usb /bin/false
```

3. Restart and connect the scanner through usb. Run `pcsc_scan` to test if it is working


### Migrations
#### Generating Migrations
1. If a model/table has been added or removed, update the import on line 9 of `alembic/env.py`
2. If database was created with create_all, delete all migrations but the first and run `alembic stamp head`
3. From the `Backend` directory, run `alembic revision --autogenerate -m "$MIGRATION_VERSION"` where $MIGRATION_VERSION is 1 + the previous version (can look in the alembic/versions directory to see)
#### Running Migrations
1. From the `Backend` directory, run `alembic run head`
#!/bin/bash

psql -v ON_ERROR_STOP=1 --host "127.0.0.1" --port 5432 --user "postgres" --dbname "postgres" <<-EOSQL
    DROP DATABASE IF EXISTS counti;
    CREATE DATABASE counti OWNER postgres ENCODING UTF8 LOCALE 'C' TEMPLATE template0;
EOSQL

rm -rf images

prisma db push

psql -v ON_ERROR_STOP=1 --host "127.0.0.1" --port 5432 --user "postgres" --dbname "counti" < seed_data.sql

cp -r seed_data_images images
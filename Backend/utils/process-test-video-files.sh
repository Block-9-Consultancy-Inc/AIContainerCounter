#!/bin/bash

INPUT_DIR=$1
OUTPUT_DIR=$2

for i in $(ls $INPUT_DIR);
    do 
        CURRENT_VIDEO=$(echo $i | cut -d "." -f 1);
        mkdir -p "$OUTPUT_DIR/$CURRENT_VIDEO";
        ffmpeg -i "$INPUT_DIR/$i" -vcodec mjpeg -qscale 1 -an "$OUTPUT_DIR/$CURRENT_VIDEO/$CURRENT_VIDEO-1920x1080.avi";
        ffmpeg -i "$INPUT_DIR/$i" -vcodec mjpeg -qscale 1 -s 1280x720 -an "$OUTPUT_DIR/$CURRENT_VIDEO/$CURRENT_VIDEO-1280x720.avi";
        ffmpeg -i "$INPUT_DIR/$i" -vcodec mjpeg -qscale 1 -s 640x480 -an "$OUTPUT_DIR/$CURRENT_VIDEO/$CURRENT_VIDEO-640x480.avi";
    done
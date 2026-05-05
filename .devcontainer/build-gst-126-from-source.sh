sudo mkdir /opt/gst-build
sudo chown vscode /opt/gst-build
cd /opt/gst-build/

wget https://github.com/mesonbuild/meson/releases/download/1.7.0/meson-1.7.0.tar.gz
tar xf meson-1.7.0.tar.gz

# Download GStreamer 1.26.0 and its core plugins
wget https://gstreamer.freedesktop.org/src/gstreamer/gstreamer-1.26.0.tar.xz
wget https://gstreamer.freedesktop.org/src/gst-plugins-base/gst-plugins-base-1.26.0.tar.xz
wget https://gstreamer.freedesktop.org/src/gst-plugins-good/gst-plugins-good-1.26.0.tar.xz
wget https://gstreamer.freedesktop.org/src/gst-plugins-bad/gst-plugins-bad-1.26.0.tar.xz
# wget https://gstreamer.freedesktop.org/src/gst-plugins-ugly/gst-plugins-ugly-1.26.0.tar.xz
# wget https://gstreamer.freedesktop.org/src/gst-libav/gst-libav-1.26.0.tar.xz

# Install docutils-0.21.2 (Python package)
pip3 install docutils==0.21.2

# Install libxslt-1.1.43
wget https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.43.tar.xz
tar -xf libxslt-1.1.43.tar.xz
cd libxslt-1.1.43
./configure --prefix=/usr           \
            --disable-static        \
            --without-python
make
sudo make install
cd ..

# Install pcre2-10.45
wget https://github.com/PCRE2Project/pcre2/releases/download/pcre2-10.45/pcre2-10.45.tar.bz2
tar -xf pcre2-10.45.tar.bz2
cd pcre2-10.45
./configure --prefix=/usr                       \
            --docdir=/usr/share/doc/pcre2-10.45 \
            --enable-unicode                    \
            --enable-jit                        \
            --enable-pcre2-16                   \
            --enable-pcre2-32                   \
            --enable-pcre2grep-libz             \
            --enable-pcre2grep-libbz2           \
            --enable-pcre2test-libreadline      \
            --disable-static
make
sudo make install
cd ..

# Install Cairo-1.18.4 dependencies first
# Install pixman (needed for Cairo)
wget https://www.cairographics.org/releases/pixman-0.44.2.tar.gz
tar -xf pixman-0.44.2.tar.gz
cd pixman-0.44.2
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr --buildtype=release ..
ninja
sudo ninja install
cd ../..

# Install libpng (needed for Cairo)
wget https://downloads.sourceforge.net/libpng/libpng-1.6.47.tar.xz
tar -xf libpng-1.6.47.tar.xz
cd libpng-1.6.47
./configure --prefix=/usr --disable-static
make
sudo make install
cd ..

# Install Cairo-1.18.4
wget https://www.cairographics.org/releases/cairo-1.18.4.tar.xz
tar -xf cairo-1.18.4.tar.xz
cd cairo-1.18.4
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
            --buildtype=release \
            -Dtee=enabled       \
            -Dtests=disabled    \
            ..
ninja
sudo ninja install
cd ../..


wget https://files.pythonhosted.org/packages/source/M/Mako/mako-1.3.9.tar.gz
tar xf mako-1.3.9.tar.gz
cd mako-1.3.9
pip3 wheel -w dist --no-build-isolation --no-deps --no-cache-dir $PWD
sudo pip3 install dist/Mako-1.3.9-py3-none-any.whl --no-user
cd ..

wget https://files.pythonhosted.org/packages/source/M/Markdown/markdown-3.7.tar.gz
tar xf markdown-3.7.tar.gz
cd markdown-3.7
pip3 wheel -w dist --no-build-isolation --no-deps --no-cache-dir $PWD
sudo pip3 install dist/Markdown-3.7-py3-none-any.whl --no-user
cd ..

pip3 install gi-docgen

# Install libxml2 dependency
wget https://download.gnome.org/sources/libxml2/2.12/libxml2-2.12.3.tar.xz
tar -xf libxml2-2.12.3.tar.xz
cd libxml2-2.12.3
./configure --prefix=/usr           \
            --disable-static        \
            --with-history          \
            --with-python=/usr/local/bin/python
make
sudo make install
cd ..

wget https://ftp.gnu.org/gnu/gsl/gsl-2.8.tar.gz
tar xf gsl-2.8.tar.gz
cd gsl-2.8
./configure --prefix=/usr --disable-static
make
cd ..

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
. "$HOME/.cargo/env"


# Install prerequisites
# GLib dependency
wget https://download.gnome.org/sources/glib/2.84/glib-2.84.0.tar.xz
wget https://download.gnome.org/sources/gobject-introspection/1.84/gobject-introspection-1.84.0.tar.xz
tar -xf glib-2.84.0.tar.xz
tar -xf gobject-introspection-1.84.0.tar.xz
cd glib-2.84.0
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup                  \
      --prefix=/usr             \
      --buildtype=release       \
      -D introspection=disabled \
      -D glib_debug=disabled    \
      -D man-pages=enabled      \
      -D sysprof=disabled         \
        ..
ninja
sudo ninja install

/opt/gst-build/meson-1.7.0/meson.py setup ../../gobject-introspection-1.84.0 gi-build \
            --prefix=/usr --buildtype=release
ninja -C gi-build
sudo ninja -C gi-build install
/opt/gst-build/meson-1.7.0/meson.py configure -D introspection=enabled
ninja

sed "/docs_dir =/s|$| / 'glib-' + meson.project_version()|" \
    -i ../docs/reference/meson.build
/opt/gst-build/meson-1.7.0/meson.py configure -D documentation=true
ninja
sudo ninja install
cd ../..


# Building GStreamer core
tar -xf gstreamer-1.26.0.tar.xz
cd gstreamer-1.26.0
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
            --buildtype=release \
            -Dgst_debug=false   \
            -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
            -Dpackage-name="GStreamer 1.26.0 BLFS" \
            ..
ninja
sudo ninja install
cd ../..

# Building GStreamer Plugins Base
tar -xf gst-plugins-base-1.26.0.tar.xz
cd gst-plugins-base-1.26.0
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
            --buildtype=release \
            -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
            -Dpackage-name="GStreamer Base Plugins 1.26.0 BLFS" \
            ..
ninja
sudo ninja install
cd ../..

# Building GStreamer Plugins Good
tar -xf gst-plugins-good-1.26.0.tar.xz
cd gst-plugins-good-1.26.0
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
            --buildtype=release \
            -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
            -Dpackage-name="GStreamer Good Plugins 1.26.0 BLFS" \
            ..
ninja
sudo ninja install
cd ../..

# # Building GStreamer Plugins Bad
tar -xf gst-plugins-bad-1.26.0.tar.xz
cd gst-plugins-bad-1.26.0
mkdir build && cd build
/opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
            --buildtype=release \
            -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
            -Dpackage-name="GStreamer Bad Plugins 1.26.0 BLFS" \
            ..
ninja
sudo ninja install
cd ../..

# # Building GStreamer Plugins Ugly
# tar -xf gst-plugins-ugly-1.26.0.tar.xz
# cd gst-plugins-ugly-1.26.0
# mkdir build && cd build
# /opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
#             --buildtype=release \
#             -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
#             -Dpackage-name="GStreamer Ugly Plugins 1.26.0 BLFS" \
#             ..
# ninja
# sudo ninja install
# cd ../..

# # Building GStreamer libav plugins (for FFmpeg integration)
# tar -xf gst-libav-1.26.0.tar.xz
# cd gst-libav-1.26.0
# mkdir build && cd build
# /opt/gst-build/meson-1.7.0/meson.py setup --prefix=/usr       \
#             --buildtype=release \
#             -Dpackage-origin=https://www.linuxfromscratch.org/blfs/view/svn/ \
#             -Dpackage-name="GStreamer Libav Plugins 1.26.0 BLFS" \
#             ..
# ninja
# sudo ninja install
# cd ../..
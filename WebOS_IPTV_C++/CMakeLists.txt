cmake_minimum_required(VERSION 3.16)
project(iptv-player-native LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Detect target: when cross-compiling with the webosbrew toolchain CMAKE_CROSSCOMPILING is true.
if(CMAKE_CROSSCOMPILING)
    set(IPTV_TARGET_WEBOS ON)
    message(STATUS "Target: webOS TV (cross)")
else()
    set(IPTV_TARGET_WEBOS OFF)
    message(STATUS "Target: host (native)")
endif()

find_package(PkgConfig REQUIRED)
find_package(Threads REQUIRED)
pkg_check_modules(SDL2 REQUIRED sdl2)
pkg_check_modules(GST REQUIRED
    gstreamer-1.0
    gstreamer-app-1.0
    gstreamer-video-1.0
)
pkg_check_modules(CURL REQUIRED libcurl)
pkg_check_modules(SQLITE REQUIRED sqlite3)
pkg_check_modules(SDL2_TTF REQUIRED SDL2_ttf)
pkg_check_modules(SDL2_IMAGE REQUIRED SDL2_image)

add_executable(iptv-player
    src/main.cpp
    src/player/GstDecoder.cpp
    src/player/Playlist.cpp
    src/xtream/XtreamClient.cpp
    src/xtream/CatalogSync.cpp
    src/store/Paths.cpp
    src/store/JsonFile.cpp
    src/store/Config.cpp
    src/store/WatchPosition.cpp
    src/store/Favorites.cpp
    src/store/WatchHistory.cpp
    src/store/Cache.cpp
    src/platform/AppLifecycle.cpp
    src/ui/TextRenderer.cpp
    src/ui/ImageLoader.cpp
    src/ui/FocusManager.cpp
    src/ui/PosterGrid.cpp
    src/ui/PlayerOSD.cpp
    src/ui/SettingsScreen.cpp
    src/ui/HomeScreen.cpp
    src/ui/SeriesDetailScreen.cpp
)

target_include_directories(iptv-player PRIVATE
    ${SDL2_INCLUDE_DIRS}
    ${SDL2_TTF_INCLUDE_DIRS}
    ${SDL2_IMAGE_INCLUDE_DIRS}
    ${GST_INCLUDE_DIRS}
    ${CURL_INCLUDE_DIRS}
    ${SQLITE_INCLUDE_DIRS}
    src
    third_party
)

target_link_libraries(iptv-player PRIVATE
    ${SDL2_LIBRARIES}
    ${SDL2_TTF_LIBRARIES}
    ${SDL2_IMAGE_LIBRARIES}
    ${GST_LIBRARIES}
    ${CURL_LIBRARIES}
    ${SQLITE_LIBRARIES}
    Threads::Threads
)

target_link_directories(iptv-player PRIVATE
    ${SDL2_LIBRARY_DIRS}
    ${SDL2_TTF_LIBRARY_DIRS}
    ${SDL2_IMAGE_LIBRARY_DIRS}
    ${GST_LIBRARY_DIRS}
    ${CURL_LIBRARY_DIRS}
    ${SQLITE_LIBRARY_DIRS}
)

target_compile_options(iptv-player PRIVATE
    ${SDL2_CFLAGS_OTHER}
    ${SDL2_TTF_CFLAGS_OTHER}
    ${SDL2_IMAGE_CFLAGS_OTHER}
    ${GST_CFLAGS_OTHER}
    ${CURL_CFLAGS_OTHER}
    ${SQLITE_CFLAGS_OTHER}
    -Wall -Wextra -Wno-unused-parameter
)

if(IPTV_TARGET_WEBOS)
    target_compile_definitions(iptv-player PRIVATE IPTV_WEBOS=1)
    # libluna-service2 ships no .pc in the webosbrew sysroot — link manually.
    target_link_libraries(iptv-player PRIVATE luna-service2 pbnjson_cpp pbnjson_c PmLogLib)
    # TV has SDL2 2.0.10 but we build against 2.30 — bundle our SDL .so in the IPK
    # and load them via rpath=$ORIGIN/lib so our binary ignores the TV copies.
    set_target_properties(iptv-player PROPERTIES
        INSTALL_RPATH "\$ORIGIN/lib"
        BUILD_RPATH   "\$ORIGIN/lib"
        BUILD_WITH_INSTALL_RPATH TRUE
    )
    install(TARGETS iptv-player RUNTIME DESTINATION usr/bin)
endif()

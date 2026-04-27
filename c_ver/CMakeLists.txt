cmake_minimum_required(VERSION 3.16)
project(quicfile CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# MsQuic must be installed system-wide or set MSQUIC_DIR
find_library(MSQUIC_LIB msquic REQUIRED)
find_path(MSQUIC_INCLUDE msquic.h PATHS /usr/include /usr/local/include)

add_executable(sender   sender.cpp)
add_executable(receiver receiver.cpp)

target_include_directories(sender   PRIVATE ${MSQUIC_INCLUDE})
target_include_directories(receiver PRIVATE ${MSQUIC_INCLUDE})
target_link_libraries(sender   ${MSQUIC_LIB})
target_link_libraries(receiver ${MSQUIC_LIB})

# Compiler hardening + speed
target_compile_options(sender   PRIVATE -O2 -Wall -Wextra)
target_compile_options(receiver PRIVATE -O2 -Wall -Wextra)
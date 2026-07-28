cmake_minimum_required(VERSION 3.15)
project(tiny_claw_accel LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 REQUIRED)

pybind11_add_module(_diff src/diff.cpp)
pybind11_add_module(_sandbox src/sandbox.cpp)

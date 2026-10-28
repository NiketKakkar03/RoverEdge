cmake_minimum_required(VERSION 3.20)
project(roveredge_native LANGUAGES CXX)

set(PYBIND11_FINDPYTHON ON)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(_native_runtime src/native_runtime.cpp)
target_compile_features(_native_runtime PRIVATE cxx_std_20)
target_compile_options(_native_runtime PRIVATE -Wall -Wextra -Wpedantic)
if(APPLE)
  target_compile_definitions(
    _native_runtime PRIVATE ROVEREDGE_HAS_ACCELERATE=1 ACCELERATE_NEW_LAPACK
  )
  target_link_libraries(_native_runtime PRIVATE "-framework Accelerate")
else()
  target_compile_definitions(_native_runtime PRIVATE ROVEREDGE_HAS_ACCELERATE=0)
endif()
set_target_properties(
  _native_runtime
  PROPERTIES
    CXX_EXTENSIONS OFF
    INTERPROCEDURAL_OPTIMIZATION OFF
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../src/roveredge"
)

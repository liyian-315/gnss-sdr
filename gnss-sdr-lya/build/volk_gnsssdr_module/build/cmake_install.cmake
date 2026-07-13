# Install script for directory: /mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/install")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/cpu_features/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "volk_gnsssdr_devel" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig" TYPE FILE FILES "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/volk_gnsssdr.pc")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "volk_gnsssdr_devel" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE DIRECTORY FILES "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/kernels/volk_gnsssdr" FILES_MATCHING REGEX "/[^/]*\\.h$")
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "volk_gnsssdr_devel" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include/volk_gnsssdr" TYPE FILE FILES
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_alloc.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_prefs.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_complex.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_common.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/saturation_arithmetic.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_avx_intrinsics.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_sse_intrinsics.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_sse3_intrinsics.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_neon_intrinsics.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/include/volk_gnsssdr/volk_gnsssdr.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/include/volk_gnsssdr/volk_gnsssdr_cpu.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/include/volk_gnsssdr/volk_gnsssdr_config_fixed.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/include/volk_gnsssdr/volk_gnsssdr_typedefs.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_malloc.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/volk_gnsssdr_sine_table.h"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr/include/volk_gnsssdr/constants.h"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "volk_gnsssdr_devel" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr" TYPE FILE FILES
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/cmake/Modules/VolkGnsssdrConfig.cmake"
    "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/cmake/Modules/VolkGnsssdrConfigVersion.cmake"
    )
endif()

if(CMAKE_INSTALL_COMPONENT STREQUAL "Unspecified" OR NOT CMAKE_INSTALL_COMPONENT)
  if(EXISTS "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr/VolkGnsssdrTargets.cmake")
    file(DIFFERENT _cmake_export_file_changed FILES
         "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr/VolkGnsssdrTargets.cmake"
         "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/CMakeFiles/Export/a9590ed132296f0268ef396b4cde4860/VolkGnsssdrTargets.cmake")
    if(_cmake_export_file_changed)
      file(GLOB _cmake_old_config_files "$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr/VolkGnsssdrTargets-*.cmake")
      if(_cmake_old_config_files)
        string(REPLACE ";" ", " _cmake_old_config_files_text "${_cmake_old_config_files}")
        message(STATUS "Old export file \"$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr/VolkGnsssdrTargets.cmake\" will be replaced.  Removing files [${_cmake_old_config_files_text}].")
        unset(_cmake_old_config_files_text)
        file(REMOVE ${_cmake_old_config_files})
      endif()
      unset(_cmake_old_config_files)
    endif()
    unset(_cmake_export_file_changed)
  endif()
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr" TYPE FILE FILES "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/CMakeFiles/Export/a9590ed132296f0268ef396b4cde4860/VolkGnsssdrTargets.cmake")
  if(CMAKE_INSTALL_CONFIG_NAME MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
    file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/volk_gnsssdr" TYPE FILE FILES "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/CMakeFiles/Export/a9590ed132296f0268ef396b4cde4860/VolkGnsssdrTargets-release.cmake")
  endif()
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/lib/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/apps/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/python/volk_gnsssdr_modtool/cmake_install.cmake")
endif()

if(CMAKE_INSTALL_COMPONENT)
  set(CMAKE_INSTALL_MANIFEST "install_manifest_${CMAKE_INSTALL_COMPONENT}.txt")
else()
  set(CMAKE_INSTALL_MANIFEST "install_manifest.txt")
endif()

string(REPLACE ";" "\n" CMAKE_INSTALL_MANIFEST_CONTENT
       "${CMAKE_INSTALL_MANIFEST_FILES}")
file(WRITE "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build/${CMAKE_INSTALL_MANIFEST}"
     "${CMAKE_INSTALL_MANIFEST_CONTENT}")

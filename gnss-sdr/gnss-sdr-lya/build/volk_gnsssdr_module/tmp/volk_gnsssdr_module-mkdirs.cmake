# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/src/algorithms/libs/volk_gnsssdr_module/volk_gnsssdr"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/build"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/install"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/tmp"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/src/volk_gnsssdr_module-stamp"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/src"
  "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/src/volk_gnsssdr_module-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/src/volk_gnsssdr_module-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/mnt/d/work/project/usrp_gnss/gnss-sdr/build/volk_gnsssdr_module/src/volk_gnsssdr_module-stamp${cfgdir}") # cfgdir has leading slash
endif()

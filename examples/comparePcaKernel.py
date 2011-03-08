#!/usr/bin/env python

# 
# LSST Data Management System
# Copyright 2008, 2009, 2010 LSST Corporation.
# 
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the LSST License Statement and 
# the GNU General Public License along with this program.  If not, 
# see <http://www.lsstcorp.org/LegalNotices/>.
#

import os
import sys
import eups
import lsst.afw.image.imageLib as afwImage
import lsst.ip.diffim as ipDiffim
import lsst.pex.logging as pexLogging
import lsst.afw.display.ds9 as ds9

display = True

verbosity = 6
pexLogging.Trace_setVerbosity("lsst.ip.diffim", verbosity)

defDataDir   = eups.productDir("afwdata") 
imageProcDir = eups.productDir("ip_diffim")

if len(sys.argv) == 1:
    defTemplatePath = os.path.join(defDataDir, "CFHT", "D4", "cal-53535-i-797722_2_tmpl")
    defSciencePath  = os.path.join(defDataDir, "CFHT", "D4", "cal-53535-i-797722_2")
elif len(sys.argv) == 3:
    defTemplatePath = sys.argv[1]
    defSciencePath  = sys.argv[2]
else:
    sys.exit(1)
    
defPolicyPath   = os.path.join(imageProcDir, "policy", "ImageSubtractStageDictionary.paf")
defOutputPath   = "diffImage"

templateMaskedImage = afwImage.MaskedImageF(defTemplatePath)
scienceMaskedImage  = afwImage.MaskedImageF(defSciencePath)
policy              = ipDiffim.generateDefaultPolicy(defPolicyPath)


# same for all kernels
policy.set("singleKernelClipping", True)
policy.set("kernelSumClipping", True)
policy.set("spatialKernelClipping", False)
policy.set("spatialKernelOrder", 0)
policy.set("spatialBgOrder", 0)
policy.set("usePcaForSpatialKernel", True)

footprints = ipDiffim.getCollectionOfFootprintsForPsfMatching(templateMaskedImage,
                                                              scienceMaskedImage,
                                                              policy)

# specific to delta function
policy.set("kernelBasisSet", "delta-function")
policy.set("useRegularization", False)
spatialKernel1, spatialBg1, kernelCellSet1 = ipDiffim.createPsfMatchingKernel(templateMaskedImage,
                                                                              scienceMaskedImage,
                                                                              policy,
                                                                              footprints[:20])

# alard lupton
policy.set("kernelBasisSet", "alard-lupton")
policy.set("useRegularization", False)
spatialKernel2, spatialBg2, kernelCellSet2 = ipDiffim.createPsfMatchingKernel(templateMaskedImage,
                                                                              scienceMaskedImage,
                                                                              policy,
                                                                              footprints[:20])

# regularized delta function
policy.set("kernelBasisSet", "delta-function")
policy.set("useRegularization", True)
spatialKernel3, spatialBg3, kernelCellSet3 = ipDiffim.createPsfMatchingKernel(templateMaskedImage,
                                                                              scienceMaskedImage,
                                                                              policy,
                                                                              footprints[:20])

basisList1 = spatialKernel1.getKernelList()
basisList2 = spatialKernel2.getKernelList()
basisList3 = spatialKernel3.getKernelList()

frame = 1
for idx in range(min(5, len(basisList1))):
    kernel = basisList1[idx]
    im     = afwImage.ImageD(spatialKernel1.getDimensions())
    ksum   = kernel.computeImage(im, False)    
    ds9.mtv(im, frame=frame)
    frame += 1

for idx in range(min(5, len(basisList2))):
    kernel = basisList2[idx]
    im     = afwImage.ImageD(spatialKernel2.getDimensions())
    ksum   = kernel.computeImage(im, False)    
    ds9.mtv(im, frame=frame)
    frame += 1


for idx in range(min(5, len(basisList3))):
    kernel = basisList3[idx]
    im     = afwImage.ImageD(spatialKernel3.getDimensions())
    ksum   = kernel.computeImage(im, False)    
    ds9.mtv(im, frame=frame)
    frame += 1


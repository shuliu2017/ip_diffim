#!/usr/bin/env python
import os
import pdb
import sys
import unittest
import lsst.utils.tests as tests

import eups
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.ip.diffim as ipDiffim
import lsst.pex.logging as logging
import lsst.ip.diffim.diffimTools as diffimTools

verbosity = 5
logging.Trace_setVerbosity('lsst.ip.diffim', verbosity)

display = False

class DiffimTestCases(unittest.TestCase):
    
    # D = I - (K.x.T + bg)
        
    def setUp(self):
        self.policy       = ipDiffim.makeDefaultPolicy()

        self.defDataDir = eups.productDir('afwdata')
        if self.defDataDir:

            defTemplatePath = os.path.join(self.defDataDir, "DC3a-Sim", "sci", "v5-e0",
                                           "v5-e0-c011-a00.sci")
            defSciencePath = os.path.join(self.defDataDir, "DC3a-Sim", "sci", "v26-e0",
                                          "v26-e0-c011-a00.sci")
            
            self.scienceImage   = afwImage.ExposureF(defSciencePath)
            self.templateImage  = afwImage.ExposureF(defTemplatePath)
            
            diffimTools.backgroundSubtract(self.policy.getPolicy("afwBackgroundPolicy"),
                                           [self.templateImage.getMaskedImage(),
                                            self.scienceImage.getMaskedImage()])
            self.offset   = 1500
            self.bbox     = afwGeom.Box2I(afwGeom.Point2I(0, self.offset),
                                          afwGeom.Point2I(511, 2046))

    def tearDown(self):
        del self.policy
        if self.defDataDir:
            del self.scienceImage
            del self.templateImage

    def testAL(self):
        self.policy.set('kernelBasisSet', 'alard-lupton')
        self.policy.set('spatialKernelOrder', 1)
        self.policy.set('spatialBgOrder', 0) # already bg-subtracted
        self.policy.set('usePcaForSpatialKernel', False)
        self.runXY0(fitForBackground = True)
        self.runXY0(fitForBackground = False)

    def testWarping(self):
        # Should fail since images are not aligned
        if not self.defDataDir:
            print >> sys.stderr, "Warning: afwdata is not set up"
            return

        templateSubImage = afwImage.ExposureF(self.templateImage, self.bbox, afwImage.LOCAL)
        scienceSubImage  = afwImage.ExposureF(self.scienceImage, self.bbox, afwImage.LOCAL)
        try:
            ipDiffim.subtractExposures(templateSubImage, scienceSubImage, self.policy, doWarping = False)
        except Exception, e:
            pass
        else:
            self.fail()

    def testNoBg(self):
        # Test not subtracting off the background
        if not self.defDataDir:
            print >> sys.stderr, "Warning: afwdata is not set up"
            return
        self.policy.set('fitForBackground', False)
        templateSubImage = afwImage.ExposureF(self.templateImage, self.bbox, afwImage.LOCAL)
        scienceSubImage  = afwImage.ExposureF(self.scienceImage, self.bbox, afwImage.LOCAL)
        try:
            ipDiffim.subtractExposures(templateSubImage, scienceSubImage, self.policy)
        except Exception, e:
            self.fail()
        else:
            pass

    def runXY0(self, fitForBackground):
        if not self.defDataDir:
            print >> sys.stderr, "Warning: afwdata is not set up"
            return

        self.policy.set('fitForBackground', fitForBackground)

        templateSubImage = afwImage.ExposureF(self.templateImage, self.bbox, afwImage.LOCAL)
        scienceSubImage  = afwImage.ExposureF(self.scienceImage, self.bbox, afwImage.LOCAL)

        # Have an XY0
        results1 = ipDiffim.subtractExposures(templateSubImage, scienceSubImage, self.policy,
                                              doWarping = True,
                                              display = display, frame = 0)
        differenceExposure1, spatialKernel1, backgroundModel1, kernelCellSet1 = results1

        # And then take away XY0
        templateSubImage.setXY0(afwGeom.Point2I(0, 0)) # do it to the exposure so the Wcs gets modified too
        scienceSubImage.setXY0(afwGeom.Point2I(0, 0))
        results2 = ipDiffim.subtractExposures(templateSubImage, scienceSubImage, self.policy,
                                              doWarping = True, 
                                              display = display, frame = 3)
        differenceExposure2, spatialKernel2, backgroundModel2, kernelCellSet2 = results2

        # need to count up the candidates first, since its a running tally
        count = 0
        for cell in kernelCellSet1.getCellList():
            for cand1 in cell.begin(False):
                count += 1

        for cell in kernelCellSet1.getCellList():
            for cand1 in cell.begin(False):
                if cand1.getStatus() == afwMath.SpatialCellCandidate.UNKNOWN:
                    continue
                if cand1.getStatus() == afwMath.SpatialCellCandidate.BAD:
                    continue
                
                cand1 = ipDiffim.cast_KernelCandidateF(cand1)
                cand2 = ipDiffim.cast_KernelCandidateF(kernelCellSet2.getCandidateById(cand1.getId()+count))

                # positions are the same
                self.assertEqual(cand1.getXCenter(), cand2.getXCenter())
                self.assertEqual(cand1.getYCenter(), cand2.getYCenter() + self.offset)

                # kernels are the same
                im1   = cand1.getKernelImage(ipDiffim.KernelCandidateF.RECENT)
                im2   = cand2.getKernelImage(ipDiffim.KernelCandidateF.RECENT)
                for y in range(im1.getHeight()):
                    for x in range(im1.getWidth()):
                        self.assertAlmostEqual(im1.get(x, y), im2.get(x, y))

        # Spatial fits are the same
        skp1 = spatialKernel1.getSpatialParameters()
        skp2 = spatialKernel2.getSpatialParameters()
        bgp1 = backgroundModel1.getParameters()
        bgp2 = backgroundModel2.getParameters()

        # first term = kernel sum, 0, 0
        self.assertAlmostEqual(skp1[0][0], skp2[0][0])
        # on other terms, the spatial terms are the same, the zpt terms are different
        for nk in range(1, len(skp1)):
            self.assertNotEqual(skp1[nk][0], skp2[nk][0])
            for np in range(1, len(skp1[nk])):
                self.assertAlmostEqual(skp1[nk][np], skp2[nk][np])

        for np in range(len(bgp1)):
            self.assertAlmostEqual(bgp1[np], bgp2[np])

#####
        
def suite():
    """Returns a suite containing all the test cases in this module."""
    tests.init()

    suites = []
    suites += unittest.makeSuite(DiffimTestCases)
    suites += unittest.makeSuite(tests.MemoryTestCase)
    return unittest.TestSuite(suites)

def run(doExit=False):
    """Run the tests"""
    tests.run(suite(), doExit)

if __name__ == "__main__":
    run(True)
    
        


     

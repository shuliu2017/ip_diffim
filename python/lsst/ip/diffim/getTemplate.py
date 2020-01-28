#
# LSST Data Management System
# Copyright 2016 LSST Corporation.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#

import numpy as np

import lsst.afw.image as afwImage
import lsst.geom as geom
import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
from lsst.ip.diffim.dcrModel import DcrModel

__all__ = ["GetCoaddAsTemplateTask", "GetCoaddAsTemplateConfig",
           "GetCalexpAsTemplateTask", "GetCalexpAsTemplateConfig"]


class GetCoaddAsTemplateConfig(pexConfig.Config):
    templateBorderSize = pexConfig.Field(
        dtype=int,
        default=10,
        doc="Number of pixels to grow the requested template image to account for warping"
    )
    coaddName = pexConfig.Field(
        doc="coadd name: typically one of 'deep', 'goodSeeing', or 'dcr'",
        dtype=str,
        default="deep",
    )
    numSubfilters = pexConfig.Field(
        doc="Number of subfilters in the DcrCoadd, used only if ``coaddName``='dcr'",
        dtype=int,
        default=3,
    )
    warpType = pexConfig.Field(
        doc="Warp type of the coadd template: one of 'direct' or 'psfMatched'",
        dtype=str,
        default="direct",
    )


class GetCoaddAsTemplateTask(pipeBase.Task):
    """Subtask to retrieve coadd for use as an image difference template.

    This is the default getTemplate Task to be run as a subtask by
    ``pipe.tasks.ImageDifferenceTask``. The main method is ``run()``.
    It assumes that coadds reside in the repository given by sensorRef.
    """

    ConfigClass = GetCoaddAsTemplateConfig
    _DefaultName = "GetCoaddAsTemplateTask"

    def run(self, exposure, sensorRef, templateIdList=None):
        """Retrieve and mosaic a template coadd exposure that overlaps the exposure

        Parameters
        ----------
        exposure: `lsst.afw.image.Exposure`
            an exposure for which to generate an overlapping template
        sensorRef : TYPE
            a Butler data reference that can be used to obtain coadd data
        templateIdList : TYPE, optional
            list of data ids (unused)

        Returns
        -------
        result : `struct`
            return a pipeBase.Struct:

            - ``exposure`` : a template coadd exposure assembled out of patches
            - ``sources`` :  None for this subtask
        """
        skyMap = sensorRef.get(datasetType=self.config.coaddName + "Coadd_skyMap")
        expWcs = exposure.getWcs()
        expBoxD = geom.Box2D(exposure.getBBox())
        expBoxD.grow(self.config.templateBorderSize)
        ctrSkyPos = expWcs.pixelToSky(expBoxD.getCenter())
        tractInfo = skyMap.findTract(ctrSkyPos)
        self.log.info("Using skyMap tract %s" % (tractInfo.getId(),))
        skyCorners = [expWcs.pixelToSky(pixPos) for pixPos in expBoxD.getCorners()]
        patchList = tractInfo.findPatchList(skyCorners)

        if not patchList:
            raise RuntimeError("No suitable tract found")
        self.log.info("Assembling %s coadd patches" % (len(patchList),))

        # compute coadd bbox
        coaddWcs = tractInfo.getWcs()
        coaddBBox = geom.Box2D()
        for skyPos in skyCorners:
            coaddBBox.include(coaddWcs.skyToPixel(skyPos))
        coaddBBox = geom.Box2I(coaddBBox)
        self.log.info("exposure dimensions=%s; coadd dimensions=%s" %
                      (exposure.getDimensions(), coaddBBox.getDimensions()))

        # assemble coadd exposure from subregions of patches
        coaddExposure = afwImage.ExposureF(coaddBBox, coaddWcs)
        coaddExposure.maskedImage.set(np.nan, afwImage.Mask.getPlaneBitMask("NO_DATA"), np.nan)
        nPatchesFound = 0
        coaddFilter = None
        coaddPsf = None
        for patchInfo in patchList:
            patchSubBBox = patchInfo.getOuterBBox()
            patchSubBBox.clip(coaddBBox)
            patchArgDict = dict(
                datasetType=self.getCoaddDatasetName() + "_sub",
                bbox=patchSubBBox,
                tract=tractInfo.getId(),
                patch="%s,%s" % (patchInfo.getIndex()[0], patchInfo.getIndex()[1]),
                numSubfilters=self.config.numSubfilters,
            )
            if patchSubBBox.isEmpty():
                self.log.info("skip tract=%(tract)s, patch=%(patch)s; no overlapping pixels" % patchArgDict)
                continue

            if self.config.coaddName == 'dcr':
                if not sensorRef.datasetExists(subfilter=0, **patchArgDict):
                    self.log.warn("%(datasetType)s, tract=%(tract)s, patch=%(patch)s,"
                                  " numSubfilters=%(numSubfilters)s, subfilter=0 does not exist"
                                  % patchArgDict)
                    continue
                patchInnerBBox = patchInfo.getInnerBBox()
                patchInnerBBox.clip(coaddBBox)
                if np.min(patchInnerBBox.getDimensions()) <= 2*self.config.templateBorderSize:
                    self.log.info("skip tract=%(tract)s, patch=%(patch)s; too few pixels." % patchArgDict)
                    continue
                self.log.info("Constructing DCR-matched template for patch %s" % patchArgDict)

                dcrModel = DcrModel.fromDataRef(sensorRef, **patchArgDict)
                # The edge pixels of the DcrCoadd may contain artifacts due to missing data.
                # Each patch has significant overlap, and the contaminated edge pixels in
                # a new patch will overwrite good pixels in the overlap region from
                # previous patches.
                # Shrink the BBox to remove the contaminated pixels,
                # but make sure it is only the overlap region that is reduced.
                dcrBBox = geom.Box2I(patchSubBBox)
                dcrBBox.grow(-self.config.templateBorderSize)
                dcrBBox.include(patchInnerBBox)
                coaddPatch = dcrModel.buildMatchedExposure(bbox=dcrBBox,
                                                           wcs=coaddWcs,
                                                           visitInfo=exposure.getInfo().getVisitInfo())
            else:
                if not sensorRef.datasetExists(**patchArgDict):
                    self.log.warn("%(datasetType)s, tract=%(tract)s, patch=%(patch)s does not exist"
                                  % patchArgDict)
                    continue
                self.log.info("Reading patch %s" % patchArgDict)
                coaddPatch = sensorRef.get(**patchArgDict)
            nPatchesFound += 1
            coaddExposure.maskedImage.assign(coaddPatch.maskedImage, coaddPatch.getBBox())
            if coaddFilter is None:
                coaddFilter = coaddPatch.getFilter()

            # Retrieve the PSF for this coadd tract, if not already retrieved
            if coaddPsf is None and coaddPatch.hasPsf():
                coaddPsf = coaddPatch.getPsf()

        if nPatchesFound == 0:
            raise RuntimeError("No patches found!")

        if coaddPsf is None:
            raise RuntimeError("No coadd Psf found!")

        coaddExposure.setPsf(coaddPsf)
        coaddExposure.setFilter(coaddFilter)
        return pipeBase.Struct(exposure=coaddExposure,
                               sources=None)

    def assembleTemplateExposure(self, butlerQC, skyMapRef, coaddExposureRefs, exposure):
        """Assemble the template exposure from the coadd patches that are received
        as inputs. Only one tract is supported.

        Parameters
        ----------
        butlerQC : `lsst.pipe.base.ButlerQuantumContext`
            Butler like object that supports getting data by DataseRef.

        skyMapRef : `lsst.daf.butler.DatasetRef`
            Reference to the SkyMap object that corresponds to the template coadd.

        coaddExposureRefs : iterable of `lsst.daf.butler.DatasetRef`
            Iterable of references to the available template coadd patches.

        exposure : `lsst.afw.image.Exposure`
            The science exposure to define the sky region of the template coadd.

        Notes
        -----
        The closest tract is selected from the skymap; multiple tracts are not
        supported. The assembled template inherits the WCS of the selected
        skymap tract and the resolution of the template exposures. Overlapping
        box regions of the input template patches are pixel by pixel copied
        into the assembled template image. There is no warping or pixel resampling.

        Pixels with no overlap of any available input patches are set to ``nan`` value
        and ``NO_DATA`` flagged.

        Returns
        -------
        exposure: `lsst.afw.image.ExposureF`
            The stiched template coadd exposure.

        """
        skyMap = butlerQC.get(skyMapRef)
        expWcs = exposure.getWcs()
        expBoxD = geom.Box2D(exposure.getBBox())
        expBoxD.grow(self.config.templateBorderSize)
        ctrSkyPos = expWcs.pixelToSky(expBoxD.getCenter())

        tractInfo = skyMap.findTract(ctrSkyPos)
        skyCorners = [expWcs.pixelToSky(pixPos) for pixPos in expBoxD.getCorners()]
        patchList = tractInfo.findPatchList(skyCorners)
        patchDict = dict(
            (tractInfo.getSequentialPatchIndex(p), p) for p in patchList
        )
        self.log.debug("Considering patches: %s" % str(patchList))

        # compute coadd bbox
        coaddWcs = tractInfo.getWcs()
        coaddBBox = geom.Box2D()
        for skyPos in skyCorners:
            coaddBBox.include(coaddWcs.skyToPixel(skyPos))
        coaddBBox = geom.Box2I(coaddBBox)
        self.log.info("exposure dimensions=%s; coadd dimensions=%s" %
                      (exposure.getDimensions(), coaddBBox.getDimensions()))

        # assemble coadd exposure from subregions of patches
        coaddExposure = afwImage.ExposureF(coaddBBox, coaddWcs)
        coaddExposure.maskedImage.set(np.nan, afwImage.Mask.getPlaneBitMask("NO_DATA"), np.nan)
        nPatchesFound = 0
        coaddFilter = None
        coaddPsf = None
        for coaddRef in coaddExposureRefs:
            dataId = coaddRef.dataId
            if dataId['tract'] == tractInfo.getId() and dataId['patch'] in patchDict:
                patchInfo = patchDict[dataId['patch']]
                self.log.info("Using template input tract=%s, patch=%s" %
                              (tractInfo.getId(), dataId['patch']))
            else:
                # This input is not among the patches for consideration
                continue

            patchSubBBox = patchInfo.getOuterBBox()
            patchSubBBox.clip(coaddBBox)
            patchArgDict = dict(
                datasetType=coaddRef.datasetType.name,
                bbox=patchSubBBox,
                tract=tractInfo.getId(),
                patch="%s,%s" % (patchInfo.getIndex()[0], patchInfo.getIndex()[1]),
                numSubfilters=self.config.numSubfilters,
            )
            if patchSubBBox.isEmpty():
                self.log.info("skip tract=%(tract)s, patch=%(patch)s; no overlapping pixels" % patchArgDict)
                continue

            # if self.config.coaddName == 'dcr':
            # TODO DM-22952
            coaddPatch = butlerQC.get(coaddRef)
            nPatchesFound += 1

            overlapBox = coaddPatch.getBBox()
            overlapBox.clip(coaddBBox)
            coaddExposure.maskedImage.assign(coaddPatch.maskedImage[overlapBox], overlapBox)

            if coaddFilter is None:
                coaddFilter = coaddPatch.getFilter()

            # Retrieve the PSF for this coadd tract, if not already retrieved
            if coaddPsf is None and coaddPatch.hasPsf():
                coaddPsf = coaddPatch.getPsf()

        if nPatchesFound == 0:
            raise RuntimeError("No patches found!")

        if coaddPsf is None:
            raise RuntimeError("No coadd Psf found!")

        coaddExposure.setPsf(coaddPsf)
        coaddExposure.setFilter(coaddFilter)
        return coaddExposure

    def getCoaddDatasetName(self):
        """Return coadd name for given task config

        Returns
        -------
        CoaddDatasetName : `string`

        TODO: This nearly duplicates a method in CoaddBaseTask (DM-11985)
        """
        warpType = self.config.warpType
        suffix = "" if warpType == "direct" else warpType[0].upper() + warpType[1:]
        return self.config.coaddName + "Coadd" + suffix


class GetCalexpAsTemplateConfig(pexConfig.Config):
    doAddCalexpBackground = pexConfig.Field(
        dtype=bool,
        default=True,
        doc="Add background to calexp before processing it."
    )


class GetCalexpAsTemplateTask(pipeBase.Task):
    """Subtask to retrieve calexp of the same ccd number as the science image SensorRef
    for use as an image difference template.

    To be run as a subtask by pipe.tasks.ImageDifferenceTask.
    Intended for use with simulations and surveys that repeatedly visit the same pointing.
    This code was originally part of Winter2013ImageDifferenceTask.
    """

    ConfigClass = GetCalexpAsTemplateConfig
    _DefaultName = "GetCalexpAsTemplateTask"

    def run(self, exposure, sensorRef, templateIdList):
        """Return a calexp exposure with based on input sensorRef.

        Construct a dataId based on the sensorRef.dataId combined
        with the specifications from the first dataId in templateIdList

        Parameters
        ----------
        exposure :  `lsst.afw.image.Exposure`
            exposure (unused)
        sensorRef : `list` of `lsst.daf.persistence.ButlerDataRef`
            Data reference of the calexp(s) to subtract from.
        templateIdList : `list` of `lsst.daf.persistence.ButlerDataRef`
            Data reference of the template calexp to be subtraced.
            Can be incomplete, fields are initialized from `sensorRef`.
            If there are multiple items, only the first one is used.

        Returns
        -------
        result : `struct`

            return a pipeBase.Struct:

                - ``exposure`` : a template calexp
                - ``sources`` : source catalog measured on the template
        """

        if len(templateIdList) == 0:
            raise RuntimeError("No template data reference supplied.")
        if len(templateIdList) > 1:
            self.log.warn("Multiple template data references supplied. Using the first one only.")

        templateId = sensorRef.dataId.copy()
        templateId.update(templateIdList[0])

        self.log.info("Fetching calexp (%s) as template." % (templateId))

        butler = sensorRef.getButler()
        template = butler.get(datasetType="calexp", dataId=templateId)
        if self.config.doAddCalexpBackground:
            templateBg = butler.get(datasetType="calexpBackground", dataId=templateId)
            mi = template.getMaskedImage()
            mi += templateBg.getImage()

        if not template.hasPsf():
            raise pipeBase.TaskError("Template has no psf")

        templateSources = butler.get(datasetType="src", dataId=templateId)
        return pipeBase.Struct(exposure=template,
                               sources=templateSources)

    def assembleTemplateExposure(self, **kwargs):
        raise NotImplementedError("Calexp template is not supported with gen3 middleware")

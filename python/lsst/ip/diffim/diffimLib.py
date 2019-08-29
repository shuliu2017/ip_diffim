#
# LSST Data Management System
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
# See the COPYRIGHT file
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
# see <https://www.lsstcorp.org/LegalNotices/>.
#

# C++ wrapper
# hoist symbols lsst.ip.diffim.detail up into lsst.ip.diffim
from .detail import *

from .basisLists import *
from ._dipoleAlgorithms import *
from .findSetBits import *
from .imageStatistics import *
from .imageSubtract import *
from .kernelCandidate import *
from .kernelCandidateDetection import *
from .kernelSolution import *

from .deprecated import deprecate_policy as _deprecate_policy


KernelCandidateF = _deprecate_policy(KernelCandidateF)
KernelCandidateDetectionF = _deprecate_policy(KernelCandidateDetectionF)
ImageStatisticsF = _deprecate_policy(ImageStatisticsF)

makeRegularizationMatrix = _deprecate_policy(makeRegularizationMatrix)
makeKernelCandidate = _deprecate_policy(makeKernelCandidate)

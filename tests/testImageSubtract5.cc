#include <fstream>

#include <boost/shared_ptr.hpp>

#include <lsst/fw/MaskedImage.h>
#include <lsst/fw/Kernel.h>
#include <lsst/fw/FunctionLibrary.h>

#include <lsst/mwi/data/Citizen.h>
#include <lsst/mwi/exceptions/Exception.h>
#include <lsst/mwi/utils/Trace.h>
#include <lsst/mwi/policy/Policy.h>
#include <lsst/mwi/policy/paf/PAFParser.h>

#include <lsst/imageproc/ImageSubtract.h>

#define DEBUG_IO 1

using namespace std;
using namespace lsst::fw;

typedef uint8 MaskT;
typedef float ImageT;
typedef double KernelT;
typedef double FuncT;

int main( int argc, char** argv )
{
    {
        lsst::mwi::utils::Trace::setDestination(cout);
        lsst::mwi::utils::Trace::setVerbosity(".", 4);

        // Read in Policy
        ifstream is("tests/ImageSubtract_policy.paf");
        lsst::mwi::policy::Policy p;
        lsst::mwi::policy::paf::PAFParser pp(p);
        pp.parse(is);
        is.close();

        // Parse policy
        KernelT convolveThreshold = static_cast<KernelT>(p.getDouble("convolveThreshold"));
        int edgeMaskBit = p.getInt("edgeMaskBit");
        unsigned int kernelRows = p.getInt("kernelRows");
        unsigned int kernelCols = p.getInt("kernelCols");
        unsigned int kernelSpatialOrder = p.getInt("kernelSpatialOrder");
        unsigned int backgroundSpatialOrder = p.getInt("backgroundSpatialOrder");
        
        // Read input images
        if (argc < 2) {
            cout << "This program takes 2 input images on the command line" << endl;
            cout << "  and finds its own detection." << endl;
            cout << "  Basis function set is delta functions." << endl;
            cout << "  There is spatial variation." << endl;
            exit(1);
        }
        string templateImage = argv[1];
        MaskedImage<ImageT,MaskT> templateMaskedImage;
        try {
            templateMaskedImage.readFits(templateImage);
        } catch (lsst::mwi::exceptions::ExceptionStack &e) {
            cerr << "Failed to open template image " << templateImage << ": " << e.what() << endl;
            return 1;
        }

        string scienceImage = argv[2];
        MaskedImage<ImageT,MaskT> scienceMaskedImage;
        try {
            scienceMaskedImage.readFits(scienceImage);
        } catch (lsst::mwi::exceptions::ExceptionStack &e) {
            cerr << "Failed to open science image " << scienceImage << ": " << e.what() << endl;
            return 1;
        }
       
        // Generate basis of delta functions for kernel
        vector<boost::shared_ptr<lsst::fw::Kernel<KernelT> > > kernelBasisVec;
        lsst::imageproc::generateDeltaFunctionKernelSet(kernelRows, kernelCols, kernelBasisVec);
        
        // Output kernel
        boost::shared_ptr<lsst::fw::LinearCombinationKernel<KernelT> > kernelPtr(
            new lsst::fw::LinearCombinationKernel<KernelT>
            );
        
        // Function for spatially varying kernel.  Make null here for this test.
        boost::shared_ptr<lsst::fw::function::Function2<FuncT> > kernelFunctionPtr(
            new lsst::fw::function::PolynomialFunction2<FuncT>(kernelSpatialOrder)
            );
        
        // Function for spatially varying background.  
        boost::shared_ptr<lsst::fw::function::Function2<FuncT> > backgroundFunctionPtr(
            new lsst::fw::function::PolynomialFunction2<FuncT>(backgroundSpatialOrder)
            );

        // Now you let the code find the peaks!
        vector<lsst::detection::Footprint::PtrType> footprintList;
        lsst::imageproc::getCollectionOfFootprintsForPsfMatching(templateMaskedImage, scienceMaskedImage, footprintList, policy);

        // Do it
        lsst::imageproc::computePsfMatchingKernelForMaskedImage
            (templateMaskedImage, scienceMaskedImage, kernelBasisVec, footprintList,
             kernelPtr, kernelFunctionPtr, backgroundFunctionPtr, p);

    }
    
    if (Citizen::census(0) == 0) {
        cerr << "No leaks detected" << endl;
    } else {
        cerr << "Leaked memory blocks:" << endl;
        Citizen::census(cerr);
    } 
}

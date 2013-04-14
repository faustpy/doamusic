#   Copyright 2013 Russell Haley
#   (Please add yourself if you make changes)
#
#   This file is part of doamusic.
#
#   doamusic is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   doamusic is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with doamusic.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function
import scipy as sp
import numpy as np
import itertools
from scipy import linalg
from scipy import misc
from scipy import pi
import util
import _music

class Estimator:
    """
    A class to carry state for estimating direction of arrival (DOA) 
    with the Multiple SIgnal Classification algorithm.
    """
    def __init__(
        self,
        antennas,
        covariance,
        field_of_view=((0,pi),(-pi,pi)),
        nsignals=None
    ):
        """
        Set up an Estimator, for making pseudospectrum plots and finding
        directions of arrival.

        Parameters
        ----------
        antennas : sequence of of N sequences of 3, or Nx3 numpy array
            Describes the relative physical positions of the array elements.
            Units are wavelength/(2*pi).

        covariance : NxN numpy array
           The joint second moment matrix.  The ij entry is the expectation of
           the product of the conjugated signal from the ith element with the
           signal from the jth element. Equal to mean[sample.H * sample].

        field_of_view : ((th_lo,th_hi),(ph_lo,ph_hi))
            Restrict the domain of DoA searches and pseudospectrum renderings.
            This is helpful to avoid aliasing from 2-dimensional arrays, or to
            avoid projection distortion in the pseudospectrum image by
            rendering only a subsection of the sphere.  Theta and phi are the
            inclination angle from the Z axis and azimuth angle from the X
            axis.

        nsignals : integer < N
            The number of incident signals, if known. Otherwise, we will try to
            estimate this from the magnitudes of the eigenvalues of the
            covariance matrix.

        """
        # Accept and validate antennas.
        self.antennas = np.array(antennas)
        self.numel = antennas.shape[0]
        assert self.antennas.shape[1] == 3      # we are operating in R3
        assert self.antennas.dtype == 'float64' # spatial coordinates
        # Accept and validate covariance.
        self.covar = np.array(covariance)
        assert self.covar.shape == (self.numel,self.numel)
        # Unpack field of view
        self.thlo,self.thhi = field_of_view[0][0],field_of_view[0][1]
        self.phlo,self.phhi = field_of_view[1][0],field_of_view[1][1]

        #Get the sorted eigenstructure
        self.eigval, self.eigvec = util.eigsort(linalg.eig(covariance))

        # Try to guess the number of incident signals, if unspecified
        if nsignals:
            assert nsignals < self.numel
            self.nsignals = nsignals
            self.noisedim = self.numel - nsignals
        else:
            shaped = abs(self.eigval)
            self.noisedim = sp.diff(shaped).argmax() + 1
            self.nsignals = self.numel - self.noisedim

        #slice the noise space
        self.noisespace = self.eigvec[:,:self.noisedim]
        self.sigspace = self.eigvec[:,self.noisedim:]
        print("Noise space dimension: {}".format(self.noisespace.shape))

    def eigplot():
        """
        Plot the eigenvalues on a logarithmic chart, for human appraisal
        of the number of incident signals (and any other interesting
        properties of the data.
        """
        pass

    def spectrum(self,(theta_sz,phi_sz),method=_music.spectrum):
        """
        Generate a MUSIC pseudospectrum on the estimator's domain. The result
        is a theta_sz x phi_sz real numpy.ndarray. The domain is a closed
        interval, like linspace.

        Parameters
        ----------
        theta_sz, phi_sz : int
            Specify the size of the result

        method : callable
            Choose between the python or cython low-level implementations.
            Used to check correctness.
        """
        # Wraps either _spectrum or _music.spectrum and provides parallel
        # evaluation.

        # precalculate static arguments as comlpex double and prepare output
        # array
        ants = self.antennas.astype(complex)
        metric = sp.atleast_2d(
                    self.noisespace.dot( self.noisespace.T.conj() )
                 ).astype(complex)
        result = np.empty((theta_sz,phi_sz))

        # step sizes
        thstep = (self.thhi-self.thlo)/(theta_sz-1)
        phstep = (self.phhi-self.phlo)/(phi_sz-1)

        method(
           metric,
           ants,
           result,
           self.thlo,thstep,theta_sz,
           self.phlo,phstep,phi_sz
        )
        return result

def doasearch(est,thetaspan,phispan,iterations=4):
    raise NotImplementedError()

def covar(samples):
    """
    Calculate the covariance matrix as used by Estimator.  
    
    This is not the same as the Octave/Matlab function cov(), but is instead
    equal to Mean [ sample.H * sample ], where sample is a single sample.
    I.E., it is actually the second moment matrix.

    Parameters
    ----------
    samples : K x Numel or Numel x 0 complex ndarray
        Complex samples for each of Numel antennas sampled at K times.

    Returns
    -------
        return : Numel x Numel complex ndarray
            Second moment matrix for complex random vector samples.  Used by
            Estimator.
    """
    samples = sp.asmatrix(samples)
    return ( (samples.H * samples) / samples.shape[0] )

def _pmusic(metric,antennas,theta,phi):
    steer = sp.exp( 1j*antennas.dot(-util.aoa2prop_scalar(theta,phi)) )
    return 1.0 / steer.conj().dot(metric).dot(steer).real

def _spectrum(
    metric,
    antennas,
    out,
    thlo,thstep,thsz,
    phlo,phstep,phsz
):
    # Lower-level spectrum calculator with preprocessed arguments and 
    # pass-by-reference output array, for easier implementation with
    # cython and being farmed out to multiple processes. (The problem is
    # embarassingly parallel.
    assert out.shape == (thsz,phsz)
    for i in xrange(thsz):
        th = thlo + i*thstep
        for j in xrange(phsz):
            ph = phlo + j*phstep
            out[i,j] = _pmusic(metric,antennas,th,ph)

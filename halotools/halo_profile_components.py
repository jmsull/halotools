# -*- coding: utf-8 -*-
"""

This module contains the classes related to 
the radial profiles of dark matter halos.

"""

__all__ = ['HaloProfileModel','NFWProfile']

from astropy.extern import six
from abc import ABCMeta, abstractmethod, abstractproperty

import numpy as np
from scipy.interpolate import UnivariateSpline as spline

from utils.array_utils import array_like_length as aph_len
import occupation_helpers as occuhelp 
import defaults

import astropy.cosmology as cosmology
from astropy import units as u

import defaults

##################################################################################


@six.add_metaclass(ABCMeta)
class HaloProfileModel(object):
    """ Container class for any halo profile model. 

    Parameters 
    ----------
    delta_vir : float
        Density of the halo enclosed by the halo boundary. Currently hard-coded to 360

    cosmology : object 
        astropy cosmology object

    redshift : float 

    Notes 
    -----
    For development purposes, object is temporarily hard-coded to only use z=0 Bryan & Norman 
    virial mass definition for standard LCDM cosmological parameter values.

    """

    def __init__(self, delta_vir, cosmology, redshift):
        self.delta_vir = 360.0
        self.redshift = 0.0
        self.cosmology = cosmology
        littleh = self.cosmology.H0/100.0
        crit_density = (
            self.cosmology.critical_density(0).to(u.Msun/u.Mpc**3)/littleh**2)
        self.cosmic_matter_density = crit_density*self.cosmology.Om0

    @abstractmethod
    def density_profile(self, r, *args):
        """ Value of the density profile evaluated at the input radius. 

        Parameters 
        ----------
        r : array_like 
            Value of the radius at which density profile is to be evaluated. 
            Should be scaled by the halo boundary, so that :math:`0 < r < 1`

        args : array_like 
            Parameters specifying the halo profile. If an array, should be of the same length 
            as the input r. 
        """
        raise NotImplementedError("All halo profile models must include a mass_density method")

    @abstractmethod
    def cumulative_mass_PDF(self, r, *args):
        """ Cumulative PDF of the halo mass profile. 

        Parameters 
        ----------
        r : array_like 
            Value of the radius at which cumulative profile is to be evaluated. 

        args : array_like 
            Parameters specifying the halo profile. If an array, should be of the same length 
            as the input r. 

        """
        raise NotImplementedError("All halo profile models must include a cumulative_mass_PDF method")


class NFWProfile(HaloProfileModel):
    """ NFW halo profile, based on Navarro, Frenk, and White (1999).

    Parameters 
    ----------
    delta_vir : float
        Density of the halo enclosed by the halo boundary. Currently hard-coded to 360

    cosmology : object 
        astropy cosmology object

    redshift : float 

    Notes 
    -----
    For development purposes, object is temporarily hard-coded to only use z=0 Bryan & Norman 
    virial mass definition for standard LCDM cosmological parameter values.

    """

    def __init__(self, 
        delta_vir=360, cosmology=cosmology.WMAP5, redshift=0.0, 
        build_inv_cumu_table=False):

        HaloProfileModel.__init__(self, delta_vir, cosmology, redshift)
        self.publication = ['arXiv:9611107']

        if build_inv_cumu_table is True:
            self.build_inv_cumu_lookup_table()


    def g(self, x):
        """ Convenience function used to evaluate the profile. 

        Parameters 
        ----------
        x : array_like 

        Returns 
        -------
        g : array_like 
            :math:`1 / g(x) = \\log(1+x) - x / (1+x)`
        """
        denominator = np.log(1.0+x) - (x/(1.0+x))
        return 1./denominator

    def rho_s(self, c):
        """ Normalization of the NFW profile. 

        Parameters 
        ----------
        c : array_like
            concentration of the profile

        Returns 
        -------
        rho_s : array_like 
            Profile normalization :math:`\\rho_{s}^{NFW} = \\frac{1}{3}\\Delta_{vir}c^{3}g(c)\\bar{\\rho}_{m}`

        """
        return (self.delta_vir/3.)*c*c*c*self.g(c)*self.cosmic_matter_density

    def density_profile(self, r, c):
        """ Mass density profile given by 
        :math:`\\rho^{NFW}(r | c) = \\rho_{s}^{NFW} / cr(1+cr)^{2}`

        Parameters 
        ----------
        r : array_like 
            Value of the radius at which density profile is to be evaluated. 
            Should be scaled by the halo boundary, so that :math: `0 < r < 1`

        c : array_like 
            Concentration specifying the halo profile. If an array, should be of the same length 
            as the input r. 
        """
        numerator = self.rho_s(c)
        denominator = (c*r)*(1.0 + c*r)*(1.0 + c*r)
        return numerator / denominator

    def cumulative_mass_PDF(self, r, c):
        """ Cumulative probability distribution of the NFW profile. 

        Parameters 
        ----------
        r : array_like 
            Value of the radius at which density profile is to be evaluated. 
            Should be scaled by the halo boundary, so that :math:`0 < r < 1`

        c : array_like 
            Concentration specifying the halo profile. If an array, should be of the same length 
            as the input r. 

        Returns 
        -------
        cumulative_PDF : array_like
            :math:`P(<r | c) = g(c) / g(c*r)`. 

        """
        return self.g(c) / self.g(r*c)

    def build_inv_cumu_lookup_table(self):

        #Set up the grid used to tabulate inverse cumulative NFW mass profiles
        #This will be used to assign halo-centric distances to the satellites
        Npts_radius = defaults.default_Npts_radius_array  
        minrad = defaults.default_min_rad 
        radius_array = np.linspace(minrad,1.,Npts_radius)
        Npts_concen = defaults.default_Npts_concen_array
        cmin = defaults.min_permitted_conc     
        cmax = defaults.max_permitted_conc     
        conc_array = np.linspace(cmin,cmax,Npts_concen)

        # After executing the following lines, 
        # self._cumu_inv_nfw_funcs will be a list of functions 
        # bound to the NFW profile object.
        # The elements of this list are functions giving spline interpolations of the 
        # inverse cumulative mass of halos with different NFW concentrations.
        # Each function takes a scalar y in [0,1] as input, 
        # and outputs the x = r/Rvir corresponding to Prob_NFW( x < r/Rvir ) = y. 
        # Thus each list element is a function object. 
        cumu_inv_funcs = []
        for c in conc_array:
            cumu_inv_funcs.append(
                spline(self.cumulative_mass_PDF(radius_array,c),radius_array))
        self.cumu_inv_func_table = np.array(cumu_inv_funcs)
        self.cumu_inv_conc_table = conc_array




















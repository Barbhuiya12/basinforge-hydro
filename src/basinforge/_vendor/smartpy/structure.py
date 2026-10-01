# This file is part of SMARTpy - An open-source rainfall-runoff model in Python
# Copyright (C) 2018-2022  Thibault Hallouin (1), Eva Mockler (1,2), Michael Bruen (1)
#
# (1) Dooge Centre for Water Resources Research, University College Dublin, Ireland
# (2) Environmental Protection Agency, Ireland
#
# SMARTpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SMARTpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SMARTpy. If not, see <http://www.gnu.org/licenses/>.


# Vendored SMARTpy 0.2.2 Python step functions; cached Numba compilation.
import numpy as np
import numba as nb

@nb.njit(cache=True)
def run_one_step_catchment(area_m2, time_gap_sec,
                           c_in_rain, c_in_peva,
                           c_p_t, c_p_c, c_p_h, c_p_d, c_p_s, c_p_z, c_p_sk, c_p_fk, c_p_gk,
                           c_s_v_ove, c_s_v_dra, c_s_v_int, c_s_v_sgw, c_s_v_dgw,
                           c_s_v_ly1, c_s_v_ly2, c_s_v_ly3, c_s_v_ly4, c_s_v_ly5, c_s_v_ly6
                           ):
    """
    This function was written by Thibault Hallouin but is largely inspired by the work of Eva Mockler, namely for
    the work published in: Mockler, E., O’Loughlin, F., and Bruen, M.: Understanding hydrological flow paths in
    conceptual catchment models using uncertainty and sensitivity analysis, Computers & Geosciences, 90, 66–77,
    doi:10.1016/j.cageo.2015.08.015, 2016.

    Catchment model * c_ *
    _ Hydrology
    ___ Inputs * in_ *
    _____ c_in_rain         precipitation as rain [mm/time step]
    _____ c_in_peva         potential evapotranspiration [mm/time step]
    ___ Parameters * p_ *
    _____ c_p_t             T: rainfall aerial correction coefficient
    _____ c_p_c             C: evaporation decay parameter
    _____ c_p_h             H: quick runoff coefficient
    _____ c_p_d             D: drain flow parameter - fraction of saturation excess diverted to drain flow
    _____ c_p_s             S: soil outflow coefficient
    _____ c_p_z             Z: effective soil depth [mm]
    _____ c_p_sk            SK: surface routing parameter [hours]
    _____ c_p_fk            FK: inter flow routing parameter [hours]
    _____ c_p_gk            GK: groundwater routing parameter [hours]
    ___ States * s_ *
    _____ c_s_v_ove         volume of water in overland store [m3]
    _____ c_s_v_dra         volume of water in drain store [m3]
    _____ c_s_v_int         volume of water in inter store [m3]
    _____ c_s_v_sgw         volume of water in shallow groundwater store [m3]
    _____ c_s_v_dgw         volume of water in deep groundwater store [m3]
    _____ c_s_v_ly1         volume of water in first soil layer store [m3]
    _____ c_s_v_ly2         volume of water in second soil layer store [m3]
    _____ c_s_v_ly3         volume of water in third soil layer store [m3]
    _____ c_s_v_ly4         volume of water in fourth soil layer store [m3]
    _____ c_s_v_ly5         volume of water in fifth soil layer store [m3]
    _____ c_s_v_ly6         volume of water in sixth soil layer store [m3]
    ___ Outputs * out_ *
    _____ c_out_aeva        actual evapotranspiration [m3/s]
    _____ c_out_q_ove       overland flow [m3/s]
    _____ c_out_q_dra       drain flow [m3/s]
    _____ c_out_q_int       inter flow [m3/s]
    _____ c_out_q_sgw       shallow groundwater flow [m3/s]
    _____ c_out_q_dgw       deep groundwater flow [m3/s]
    """

    # # 1. Hydrology
    # # 1.0. Define internal constants
    nb_soil_layers = 6.0  # number of layers in soil column [-]

    # # 1.1. Convert non-SI units
    c_p_sk *= 3600.0  # convert hours in seconds
    c_p_fk *= 3600.0  # convert hours in seconds
    c_p_gk *= 3600.0  # convert hours in seconds

    # # 1.2. Hydrological calculations

    # /!\ all calculations in mm equivalent until further notice

    # calculate capacity Z and level LVL of each layer (assumed equal) from effective soil depth
    list_z_lyr = [
        0.0,  # artificial null value added to keep script clear later
        c_p_z / nb_soil_layers,  # Soil Layer 1
        c_p_z / nb_soil_layers,  # Soil Layer 2
        c_p_z / nb_soil_layers,  # Soil Layer 3
        c_p_z / nb_soil_layers,  # Soil Layer 4
        c_p_z / nb_soil_layers,  # Soil Layer 5
        c_p_z / nb_soil_layers  # Soil Layer 6
    ]

    list_lvl_lyr = [  # factor 1000 to convert m in mm
        0.0,  # artificial null value added to keep script clear later
        c_s_v_ly1 / area_m2 * 1e3,  # Soil Layer 1
        c_s_v_ly2 / area_m2 * 1e3,  # Soil Layer 2
        c_s_v_ly3 / area_m2 * 1e3,  # Soil Layer 3
        c_s_v_ly4 / area_m2 * 1e3,  # Soil Layer 4
        c_s_v_ly5 / area_m2 * 1e3,  # Soil Layer 5
        c_s_v_ly6 / area_m2 * 1e3  # Soil Layer 6
    ]

    # calculate cumulative level of water in all soil layers at beginning of time step (i.e. soil moisture)
    lvl_total_start = sum(list_lvl_lyr)

    # apply parameter T to rainfall data (aerial rainfall correction)
    rain = c_in_rain * c_p_t
    # calculate excess rainfall
    excess_rain = rain - c_in_peva
    # initialise actual evapotranspiration variable
    aeva = 0.0

    if excess_rain >= 0.0:  # excess rainfall available for runoff and infiltration
        # actual evapotranspiration = potential evapotranspiration
        aeva += c_in_peva
        # calculate surface runoff using quick runoff parameter H and relative soil moisture content
        h_prime = c_p_h * (lvl_total_start / c_p_z)
        overland_flow = h_prime * excess_rain  # excess rainfall contribution to quick surface runoff store
        excess_rain -= overland_flow  # remainder that infiltrates
        # calculate percolation through soil layers (from top layer [1] to bottom layer [6])
        for i in [1, 2, 3, 4, 5, 6]:
            space_in_lyr = list_z_lyr[i] - list_lvl_lyr[i]
            if excess_rain <= space_in_lyr:
                list_lvl_lyr[i] += excess_rain
                excess_rain = 0.0
            else:
                list_lvl_lyr[i] = list_z_lyr[i]
                excess_rain -= space_in_lyr
        # calculate saturation excess from remaining excess rainfall after filling layers (if not 0)
        drain_flow = c_p_d * excess_rain  # sat. excess contribution (if not 0) to quick interflow runoff store
        inter_flow = (1.0 - c_p_d) * excess_rain  # sat. excess contribution (if not 0) to slow interflow runoff store
        # calculate leak from soil layers (i.e. piston flow becoming active during rainfall events)
        s_prime = c_p_s * (lvl_total_start / c_p_z)
        # leak to interflow
        for i in [1, 2, 3, 4, 5, 6]:  # soil moisture outflow reducing exponentially downwards
            leak_interflow = list_lvl_lyr[i] * (s_prime ** i)
            if leak_interflow < list_lvl_lyr[i]:
                inter_flow += leak_interflow  # soil moisture outflow contribution to slow interflow runoff store
                list_lvl_lyr[i] -= leak_interflow
        # leak to shallow groundwater flow
        shallow_flow = 0.0
        for i in [1, 2, 3, 4, 5, 6]:  # soil moisture outflow reducing linearly downwards
            leak_shallow_flow = list_lvl_lyr[i] * (s_prime / i)
            if leak_shallow_flow < list_lvl_lyr[i]:
                shallow_flow += leak_shallow_flow  # soil moisture outflow contribution to slow shallow GW runoff store
                list_lvl_lyr[i] -= leak_shallow_flow
        # leak to deep groundwater flow
        deep_flow = 0.0
        for i in [6, 5, 4, 3, 2, 1]:  # soil moisture outflow reducing exponentially upwards
            leak_deep_flow = list_lvl_lyr[i] * (s_prime ** (7 - i))
            if leak_deep_flow < list_lvl_lyr[i]:
                deep_flow += leak_deep_flow  # soil moisture outflow contribution to slow deep GW runoff store
                list_lvl_lyr[i] -= leak_deep_flow
    else:  # no excess rainfall (i.e. potential evapotranspiration not satisfied by available rainfall)
        overland_flow = 0.0  # no soil moisture contribution to quick overland flow runoff store
        drain_flow = 0.0  # no soil moisture contribution to quick drain flow runoff store
        inter_flow = 0.0  # no soil moisture contribution to quick + leak interflow runoff store
        shallow_flow = 0.0  # no soil moisture contribution to shallow groundwater flow runoff store
        deep_flow = 0.0  # no soil moisture contribution to deep groundwater flow runoff store

        deficit_rain = excess_rain * (-1.0)  # excess is negative => excess is actually a deficit
        aeva += rain
        for i in [1, 2, 3, 4, 5, 6]:  # attempt to satisfy PE from soil layers (from top layer [1] to bottom layer [6]
            if list_lvl_lyr[i] >= deficit_rain:  # i.e. all moisture required available in this soil layer
                list_lvl_lyr[i] -= deficit_rain  # soil layer is reduced by the moisture required
                aeva += deficit_rain  # this moisture contributes to the actual evapotranspiration
                deficit_rain = 0.0  # the full moisture still required has been met
            else:  # i.e. not all moisture required available in this soil layer
                aeva += list_lvl_lyr[i]  # takes what is available in this layer for evapotranspiration
                # effectively reduce the evapotranspiration demand for the next layer using parameter C
                # i.e. the more you move down through the soil layers, the less AET can meet PET (exponentially)
                deficit_rain = c_p_c * (deficit_rain - list_lvl_lyr[i])
                list_lvl_lyr[i] = 0.0  # soil layer is now empty

    # /!\ all calculations in S.I. units now (i.e. mm converted into cubic metres)

    # calculate actual evapotranspiration as a flux
    c_out_aeva = aeva / 1e3 * area_m2 / time_gap_sec  # [m3/s]

    # route overland flow (quick surface runoff)
    c_out_q_h2o_ove = c_s_v_ove / c_p_sk  # [m3/s]
    c_s_v_ove += (overland_flow / 1e3 * area_m2) - (c_out_q_h2o_ove * time_gap_sec)  # [m3] - [m3]
    if c_s_v_ove < 0.0:
        c_s_v_ove = 0.0
    # route drain flow (quick interflow runoff)
    c_out_q_h2o_dra = c_s_v_dra / c_p_sk  # [m3/s]
    c_s_v_dra += (drain_flow / 1e3 * area_m2) - (c_out_q_h2o_dra * time_gap_sec)  # [m3] - [m3]
    if c_s_v_dra < 0.0:
        c_s_v_dra = 0.0
    # route interflow (slow interflow runoff)
    c_out_q_h2o_int = c_s_v_int / c_p_fk  # [m3/s]
    c_s_v_int += (inter_flow / 1e3 * area_m2) - (c_out_q_h2o_int * time_gap_sec)  # [m3] - [m3]
    if c_s_v_int < 0.0:
        c_s_v_int = 0.0
    # route shallow groundwater flow (slow shallow GW runoff)
    c_out_q_h2o_sgw = c_s_v_sgw / c_p_gk  # [m3/s]
    c_s_v_sgw += (shallow_flow / 1e3 * area_m2) - (c_out_q_h2o_sgw * time_gap_sec)  # [m3] - [m3]
    if c_s_v_sgw < 0.0:
        c_s_v_sgw = 0.0
    # route deep groundwater flow (slow deep GW runoff)
    c_out_q_h2o_dgw = c_s_v_dgw / c_p_gk  # [m3/s]
    c_s_v_dgw += (deep_flow / 1e3 * area_m2) - (c_out_q_h2o_dgw * time_gap_sec)  # [m3] - [m3]
    if c_s_v_dgw < 0.0:
        c_s_v_dgw = 0.0

    # # 1.3. Return outputs and states
    return (
        c_out_aeva, c_out_q_h2o_ove, c_out_q_h2o_dra, c_out_q_h2o_int, c_out_q_h2o_sgw, c_out_q_h2o_dgw,
        c_s_v_ove, c_s_v_dra, c_s_v_int, c_s_v_sgw, c_s_v_dgw,
        list_lvl_lyr[1] / 1e3 * area_m2, list_lvl_lyr[2] / 1e3 * area_m2, list_lvl_lyr[3] / 1e3 * area_m2,
        list_lvl_lyr[4] / 1e3 * area_m2, list_lvl_lyr[5] / 1e3 * area_m2, list_lvl_lyr[6] / 1e3 * area_m2
    )


@nb.njit(cache=True)
def run_one_step_river(time_gap_sec,
                       r_in_q_riv, r_p_rk, r_s_v_riv):
    """
    This function was written by Thibault Hallouin but is largely inspired by the work of Eva Mockler, namely for
    the work published in: Mockler, E., O’Loughlin, F., and Bruen, M.: Understanding hydrological flow paths in
    conceptual catchment models using uncertainty and sensitivity analysis, Computers & Geosciences, 90, 66–77,
    doi:10.1016/j.cageo.2015.08.015, 2016.

    River model * r_ *
    _ Hydrology
    ___ Inputs * in_ *
    _____ r_in_q_riv      flow at inlet [m3/s]
    ___ Parameters * p_ *
    _____ r_p_rk          linear factor k for water where Storage = k.Flow [hours]
    ___ States * s_ *
    _____ r_s_v_riv       volume of water in store [m3]
    ___ Outputs * out_ *
    _____ r_out_q_riv     flow at outlet [m3/s]
    """
    # # 1. Hydrology
    # # 1.0. Define internal constants
    r_p_rk *= 3600.0  # convert hours in seconds

    # # 1.1. Hydrological calculations

    # calculate outflow, at current time step
    r_out_q_riv = r_s_v_riv / r_p_rk
    # calculate storage in temporary variable, for next time step
    r_s_v_h2o_old = r_s_v_riv
    r_s_v_h2o_temp = r_s_v_h2o_old + (r_in_q_riv - r_out_q_riv) * time_gap_sec
    # check if storage has gone negative
    if r_s_v_h2o_temp < 0.0:  # temporary cannot be used
        # constrain outflow: allow maximum outflow at 95% of what was in store
        r_out_q_riv = 0.95 * (r_in_q_riv + r_s_v_h2o_old / time_gap_sec)
        # calculate final storage with constrained outflow
        r_s_v_riv += (r_in_q_riv - r_out_q_riv) * time_gap_sec
    else:
        r_s_v_riv = r_s_v_h2o_temp  # temporary storage becomes final storage

    # # 1.2. Return output and state
    return (
        r_out_q_riv, r_s_v_riv
    )

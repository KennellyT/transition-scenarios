import sys
import jinja2
import numpy as np
import os
import pandas as pd
import csv
import collections
import matplotlib.pyplot as plt
import sqlite3 as lite
from itertools import cycle
import matplotlib
from matplotlib import cm
import pyne
from pyne import nucname
from operator import itemgetter


def get_cursor(file_name):
    """
    Connects and returns a cursor to an sqlite output file

    Inputs:

    file_name: str
        name of the sqlite file

    Outputs:

    sqlite cursor3
    """

    # a cursor is made that points to the sqlite file named "file_name"
    con = lite.connect(file_name)
    con.row_factory = lite.Row

    return con.cursor()


def get_agent_ids(cur, archetype):
    """
    Gets all agentIds from Agententry table for wanted archetype

        agententry table has the following format:
            SimId / AgentId / Kind / Spec /
            Prototype / ParentID / Lifetime / EnterTime

    Inputs:

    cur: cursor
        sqlite cursor3

    archetype: str
        agent's archetype specification

    Outputs:

    id_list: list
        list of all agentId strings
    """
    # note that this gets agent IDs, not the IDs of a specific prototype.
    # using the cursor to access the right file, .execute goes to the file and
    # performs the command in " ".  Note that the command is not for python at
    # all - it is SQL subscripting.
    agents = cur.execute("SELECT agentid FROM agententry WHERE spec "
                         "LIKE '%" + archetype + "%' COLLATE NOCASE"
                         ).fetchall()

    return list(str(agent['agentid']) for agent in agents)


def get_prototype_id(cur, prototype):
    """
    Returns agentid of a prototype

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    prototype: str
        name of prototype

    Outputs:
    agent_id: list
        list of prototype agent_ids as strings
    """

    # like get-agent_ids, this uses the cursor to access the sqlite file, then it performs the
    # command in .execute.
    ids = cur.execute('SELECT agentid FROM agententry '
                      'WHERE prototype = "' +
                      str(prototype) + '" COLLATE NOCASE').fetchall()

    return list(str(agent['agentid']) for agent in ids)


def get_timesteps(cur):
    """
    Returns simulation start year, month, duration and
    timesteps (in numpy linspace).

    Inputs:
    cur: sqlite cursor
        sqlite cursor

    Outputs:
    init_year: int
        start year of simulation
    init_month: int
        start month of simulation
    duration: int
        duration of simulation
    timestep: list
        linspace up to duration
    """

    # this executes the command, and assigns the data from this query to info
    info = cur.execute('SELECT initialyear, initialmonth, '
                       'duration FROM info').fetchone()

    # then, the separate variables init_year, init_month, and duration are found by
    # indexing info at the correct header.  Notice that the .execute command selects "initialyear", "initialmonth"
    # etc., and these names are exactly what the function uses to index info.  timestep is found using the
    # numpy (as np) linspace function.
    init_year = info['initialyear']
    init_month = info['initialmonth']
    duration = info['duration']
    timestep = np.linspace(0, duration - 1, num=duration)

    return init_year, init_month, duration, timestep


def get_timeseries(in_list, duration, kg_to_tons):
    """
    Returns a timeseries list from in_list data.

    Inputs:
    in_list: list
        list of data to be created into timeseries
        list[0] = time
        list[1] = value, quantity
    duration: int
        duration of the simulation
    kg_to_tons: bool
        if True, list returned has units of tons
        if False, list returned as units of kilograms

    Outputs:
    timeseries list of commodities stored in in_list
    """

    # given a data input, it puts the data into a list of the data quantity
    # over time
    value = 0
    value_timeseries = []
    array = np.array(in_list)
    if len(in_list) > 0:
        for i in range(0, duration):
            value = sum(array[array[:, 0] == i][:, 1])
            if kg_to_tons:
                value_timeseries.append(value * 0.001)
            else:
                value_timeseries.append(value)
    return value_timeseries


def get_timeseries_cum(in_list, duration, kg_to_tons):
    """
    Returns a timeseries list from in_list data.

    Inputs:
    in_list: list
        list of data to be created into timeseries
        list[0] = time
        list[1] = value, quantity
    multiplyby: int
        integer to multiply the value in the list by for
        unit conversion from kilograms
    kg_to_tons: bool
        if True, list returned has units of tons
        if False, list returned as units of kilograms

    Outputs:
    timeseries of commodities in kg or tons
    """

    # as get_timeseries, but a cumulative time series of the quantity
    value = 0
    value_timeseries = []
    array = np.array(in_list)
    if len(in_list) > 0:
        for i in range(0, duration):
            value += sum(array[array[:, 0] == i][:, 1])
            if kg_to_tons:
                value_timeseries.append(value * 0.001)
            else:
                value_timeseries.append(value)
    return value_timeseries


def exec_string(in_list, search, request_colmn):
    """Generates sqlite query command to select things and
        inner join resources and transactions.

    Inputs:
    in_list: list
        list of items to specify search
        This variable will be inserted as sqlite
        query arugment following the search keyword
    search: str
        criteria for in_list search
        This variable will be inserted as sqlite
        query arugment following the WHERE keyword
    request_colmn: str
        column (set of values) that the sqlite query should return
        This variable will be inserted as sqlite
        query arugment following the SELECT keyword

    Outputs:
    query: str
        sqlite query command.
    """

    # this function isn't used on its own - rather it's used within other functions to execute
    # complex queries on the resources and transaction tables.
    if len(in_list) == 0:
        raise Exception('Cannot create an exec_string with an empty list')
    if isinstance(in_list[0], str):
        in_list = ['"' + x + '"' for x in in_list]

    query = ("SELECT " + request_colmn +
             " FROM resources INNER JOIN transactions"
             " ON transactions.resourceid = resources.resourceid"
             " WHERE (" + str(search) + ' = ' + str(in_list[0])
             )
    for item in in_list[1:]:
        query += ' OR ' + str(search) + ' = ' + str(item)
    query += ')'

    return query


def get_isotope_transactions(resources, compositions):
    """Creates a dictionary with isotope name, mass, and time

    Inputs:
    resources: list of tuples
        resource data from the resources table
        (times, sum(quantity), qualid)
    compositions: list of tuples
        composition data from the compositions table
        (qualid, nucid, massfrac)

    Outputs:
    transactions: dictionary
        dictionary with "key=isotope, and
        value=list of tuples (time, mass)
    """

    # transactions is a dictionary object where the key is the isotope name, and values is a list of tuples
    # in the format (time, mass).  time is in months, and mass is in kg.
    transactions = collections.defaultdict(list)
    for res in resources:
        for comp in compositions:
            if res['qualid'] == comp['qualid']:
                transactions[comp['nucid']].append((res['time'],
                                                    res['sum(quantity)'] *
                                                    comp['massfrac']))

    return transactions


def get_waste_dict(isotope_list, time_mass_list, duration):
    """Given an isotope, mass and time list, creates a dictionary
       With key as isotope and time series of the isotope mass.

    Inputs:
    isotope_list: list
        list with all the isotopes from resources table
    time_mass_list: list
        a list of lists.  each outer list corresponds to a different isotope
        and contains tuples in the form (time,mass) for the isotope transaction.
    duration: integer
        simulation duration

    Outputs:
    waste_dict: dictionary
        dictionary with "key=isotope, and
        value=mass timeseries of each unique isotope"
    """

    # first, the individual key strings are pulled into an array, which makes
    # it easier to use them later
    keys = []
    for key in isotope_list:
        keys.append(key)

    # initialize waste_dict
    waste_dict = {}

    # the next steps are the same for any number of isotopes in the recipe, but
    # if there is more than one, a loop is added to accommodate having multple
    # isotopes.

    # this function, in practice, is called using the data from the get_isotope_transactions
    # function.  If you look at this data, you will notice that when there was no
    # event, i.e., no influx or outflux of material, the data point for that time step does not exist.
    # this is not particularly helpful for plotting data.  The steps below pull out the time and mass
    # values from within the tuple, and create separate arrays of each (called times and masses, respectively)
    # then, in order to "fill in" the data points in which there were no events, new arrays, called times1
    # masses1, are created.  An empty array called nums is also made, which is the length of the simulation duration.
    # then, a loop is used to check if the timestep in nums is already in times1.  If it is not, the .insert function
    # is used to put the data point into the correct position, and similarly, a data point is inserted in masses1 in
    # this position, with a value of 0
    if len(time_mass_list) == 1:
        times = []
        masses = []
        for i in list(time_mass_list[0]):
            time = str(i).split(',')[0]
            times.append((float(time.strip('('))))
            mass = str(i).split(',')[1]
            masses.append((float(mass.strip(')').strip('('))))

        times1 = times
        masses1 = masses
        nums = np.arange(0, duration)

        for j in nums:
            if j not in times1:
                times1.insert(j, j)
                masses1.insert(j, 0)

        waste_dict[key] = masses1

    else:
        for element in range(len(time_mass_list)):
            times = []
            masses = []
            for i in list(time_mass_list[element]):
                time = str(i).split(',')[0]
                times.append((float(time.strip('('))))
                mass = str(i).split(',')[1]
                masses.append((float(mass.strip(')').strip('('))))

            times1 = times
            masses1 = masses
            nums = np.arange(0, duration)

            for j in nums:
                if j not in times1:
                    times1.insert(j, j)
                    masses1.insert(j, 0)

            waste_dict[keys[element]] = masses1

    return waste_dict


def plot_in_out_flux(
        cur,
        facility,
        influx_bool,
        title,
        is_cum=False,
        is_tot=False):
    """plots timeseries influx/ outflux from facility name in kg.

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    facility: str
        facility name
    influx_bool: bool
        if true, calculates influx,
        if false, calculates outflux
    title: str
        title of the multi line plot
    outputname: str
        filename of the multi line plot file
    is_cum: Boolean:
        true: add isotope masses over time
        false: do not add isotope masses at each timestep

    Outputs:
    none
    """

    # first, the id of the prototype in question is pulled using
    # get_prototype_id
    agent_ids = get_prototype_id(cur, facility)

    # then, the resources array is found using exec_string.  note that if influx+bool is
    # true (the function is plotting influx), exec_string uses recieverId.  If, instead,
    # the influx_bool is false, and outflux is being plotted, exec_string uses
    # senderId
    if influx_bool is True:
        resources = cur.execute(exec_string(agent_ids,
                                            'transactions.receiverId',
                                            'time, sum(quantity), '
                                            'qualid') +
                                ' GROUP BY time, qualid').fetchall()
    else:
        resources = cur.execute(exec_string(agent_ids,
                                            'transactions.senderId',
                                            'time, sum(quantity), '
                                            'qualid') +
                                ' GROUP BY time, qualid').fetchall()

    # then, isotope composition data is collected from the SQL tables.
    compositions = cur.execute('SELECT qualid, nucid, massfrac '
                               'FROM compositions').fetchall()

    # simulation data is pulled using get_timesteps
    init_year, init_month, duration, timestep = get_timesteps(cur)

    # data on the time of each material transaction and the amount of material moved during the transaction
    # for each isotope is pulled using get_isotope_transactions.
    transactions = get_isotope_transactions(resources, compositions)

    # because transactions is a dictionary, it is easier to manipulate the data if the values are first
    # pulled out and appended to an array.  time_mass is an array of arrays, with each sub array corresponding
    # to each value entry from transactions.
    time_mass = []
    time_waste = {}
    for key in transactions.keys():

        time_mass.append(transactions[key])
        time_waste[key] = transactions[key]
    # waste_dict then takes the data from time_mass, fills in the missing data points,
    # and returns a dictionary with key = isotope and value = time series of
    # isotope mass.
    waste_dict = get_waste_dict(transactions.keys(),
                                time_mass,
                                duration)

    # the following plots the material transaction data based on the cumulative and total
    # options chosen by the user.  Because mass values of zero actually correspond to no event
    # taking place, these values are converted to nan and therefore, not
    # plotted.
    if is_cum == False and is_tot == False:
        keys = []
        for key in waste_dict.keys():
            keys.append(key)

        for element in range(len(keys)):
            time_and_mass = np.array(time_waste[keys[element]])
            time = [item[0] for item in time_and_mass]
            mass = [item[1] for item in time_and_mass]
            plt.plot(
                time,
                mass,
                linestyle=' ',
                marker='.',
                markersize=1,
                label=nucname.name(
                    keys[0]))
# =============================================================================
#         for element in range(len(keys)):
#             mass = np.array(waste_dict[keys[element]])
#             mass[mass == 0] = np.nan
#             plt.plot(mass, linestyle = ' ',marker = '.',markersize = 1, label = keys[element])
#             plt.plot(time_list,mass_list)
# =============================================================================
        plt.legend(loc='upper left')
        plt.title(title)
        plt.xlabel('time [months]')
        plt.ylabel('mass [kg]')
        plt.xlim(left=0.0)
        plt.ylim(bottom=0.0)
        plt.show()

    elif is_cum and is_tot == False:
        value = 0
        keys = []
        for key in waste_dict.keys():
            keys.append(key)

        for element in range(len(waste_dict.keys())):
            placeholder = []
            value = 0
            key = keys[element]

            for index in range(len(waste_dict[key])):
                value += waste_dict[key][index]
                placeholder.append(value)
            waste_dict[key] = placeholder

        times = []
        nuclides = []
        masstime = {}
        for element in range(len(keys)):
            time_and_mass = np.array(time_waste[keys[element]])
            time = [item[0] for item in time_and_mass]
            mass = [item[1] for item in time_and_mass]
            nuclide = nucname.name(keys[element])
            mass_cum = np.cumsum(mass)
            times.append(time)
            nuclides.append(str(nuclide))
            masstime[nucname.name(keys[element])] = mass_cum
        mass_sort = sorted(masstime.items(), key=lambda e: e[
                           1][-1], reverse=True)
        nuclides = [item[0] for item in mass_sort]
        masses = [item[1] for item in mass_sort]
        plt.stackplot(times[0], masses, labels=nuclides)
        plt.legend(loc='upper left')
        plt.title(title)
        plt.xlabel('time [months]')
        plt.ylabel('mass [kg]')
        plt.xlim(left=0.0)
        plt.ylim(bottom=0.0)
        plt.show()

    elif is_cum == False and is_tot == True:
        keys = []
        for key in waste_dict.keys():
            keys.append(key)

        total_mass = np.zeros(len(waste_dict[keys[0]]))
        for element in range(len(keys)):
            for index in range(len(waste_dict[keys[0]])):
                total_mass[index] += waste_dict[keys[element]][index]

        total_mass[total_mass == 0] = np.nan
        plt.plot(total_mass, linestyle=' ', marker='.', markersize=1)
        plt.title(title)
        plt.xlabel('time [months]')
        plt.ylabel('mass [kg]')
        plt.xlim(left=0.0)
        plt.ylim(bottom=0.0)
        plt.show()

    elif is_cum and is_tot:
        value = 0
        keys = []
        for key in waste_dict.keys():
            keys.append(key)

        times = []
        nuclides = []
        masstime = {}
        for element in range(len(keys)):
            time_and_mass = np.array(time_waste[keys[element]])
            time = [item[0] for item in time_and_mass]
            mass = [item[1] for item in time_and_mass]
            nuclide = nucname.name(keys[element])
            mass_cum = np.cumsum(mass)
            times.append(time)
            nuclides.append(str(nuclide))
            masstime[nucname.name(keys[element])] = mass_cum
        mass_sort = sorted(masstime.items(), key=lambda e: e[
                           1][-1], reverse=True)
        nuclides = [item[0] for item in mass_sort]
        masses = [item[1] for item in mass_sort]
        plt.stackplot(times[0], masses, labels=nuclides)
        plt.legend(loc='upper left')
        plt.title(title)
        plt.xlabel('time [months]')
        plt.ylabel('mass [kg]')
        plt.xlim(left=0.0)
        plt.ylim(bottom=0.0)
        plt.show()


def u_util_calc(cur):
    """Returns fuel utilization factor of fuel cycle

    Inputs:
    cur: sqlite cursor
        sqlite cursor

    Outputs:
    u_util_timeseries: numpy array
        Timeseries of Uranium utilization factor

    Prints simulation average Uranium Utilization
    """
    # timeseries of natural uranium
    u_supply_timeseries = np.array(nat_u_timeseries(cur))

    # timeseries of fuel into reactors
    fuel_timeseries = np.array(fuel_into_reactors(cur))

    # timeseries of Uranium utilization
    u_util_timeseries = np.nan_to_num(fuel_timeseries / u_supply_timeseries)
    print('The Average Fuel Utilization Factor is: ')
    print(sum(u_util_timeseries) / len(u_util_timeseries))

    plt.plot(u_util_timeseries)
    plt.xlabel('time [months]')
    plt.ylabel('Uranium Utilization')
    plt.show()

    return u_util_timeseries


def nat_u_timeseries(cur, is_cum=True):
    """Finds natural uranium supply from source
        Since currently the source supplies all its capacity,
        the timeseriesenrichmentfeed is used.

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Outputs:
    get_timeseries: function
        calls a function that returns timeseries list of natural U
        demand from enrichment [MTHM]
    """
    init_year, init_month, duration, timestep = get_timesteps(cur)

    # Get Nat U feed to enrichment from timeseriesenrichmentfeed
    feed = cur.execute('SELECT time, sum(value) '
                       'FROM timeseriesenrichmentfeed '
                       'GROUP BY time').fetchall()
    if is_cum:
        return get_timeseries_cum(feed, duration, True)
    else:
        return get_timeseries(feed, duration, True)


def fuel_into_reactors(cur, is_cum=True):
    """Finds timeseries of mass of fuel received by reactors

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Outputs:
    timeseries list of fuel into reactors [tons]
    """

    # first, get time data from the simulation using get_timesteps
    init_year, init_month, duration, timestep = get_timesteps(cur)
    fuel = cur.execute('SELECT time, sum(quantity) FROM transactions '
                       'INNER JOIN resources ON '
                       'resources.resourceid = transactions.resourceid '
                       'INNER JOIN agententry ON '
                       'transactions.receiverid = agententry.agentid '
                       'WHERE spec LIKE "%Reactor%" '
                       'GROUP BY time').fetchall()

    if is_cum:
        return get_timeseries_cum(fuel, duration, True)
    else:
        return get_timeseries(fuel, duration, True)


def plot_swu(cur, is_cum=True):
    """returns dictionary of swu timeseries for each enrichment plant

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Outputs:
    swu_dict: dictionary
        dictionary with "key=Enrichment (facility number), and
        value=swu timeseries list"
    """

    # first, an empty dictionary is created.  then, the IDs of each enrichment plant is pulled, and
    # the simulation time data are retrieved using get_timesteps.
    swu_dict = {}
    agentid = get_agent_ids(cur, 'Enrichment')
    init_year, init_month, duration, timestep = get_timesteps(cur)

    # then, for each agent ID pulled from the CYCLUS data, the SWU data for that ID is fetched from the SQL
    # database and assigned to swu_data.  Then, this data is put into timeseries form.  This final timeseries
    # format of the data is what is actually assigned to the value in the
    # swu_dict dictionary.
    for num in agentid:
        swu_data = cur.execute('SELECT time, value '
                               'FROM timeseriesenrichmentswu '
                               'WHERE agentid = ' + str(num)).fetchall()
        if is_cum:
            swu_timeseries = get_timeseries_cum(swu_data, duration, False)
        else:
            swu_timeseries = get_timeseries(swu_data, duration, False)

        swu_dict['Enrichment_' + str(num)] = swu_timeseries

    # below, the data from swu_dict is plotted.
    keys = []
    for key in swu_dict.keys():
        keys.append(key)

    if len(swu_dict) == 1:

        if is_cum:

            plt.plot(swu_dict[keys[0]], linestyle='-', linewidth=1)
            plt.title('SWU: cumulative')
            plt.xlabel('time [months]')
            plt.ylabel('SWU')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()

        else:

            limit = 10**25
            swu = np.array(swu_dict[keys[0]])
            swu[swu > limit] = np.nan
            swu[swu == 0] = np.nan
            plt.plot(swu, linestyle=' ', marker='.', markersize=1)
            plt.title('SWU: noncumulative')
            plt.xlabel('time [months]')
            plt.ylabel('SWU')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()

    else:

        if is_cum:
            for element in range(len(keys)):
                plt.plot(
                    swu_dict[
                        keys[element]],
                    linestyle='-',
                    linewidth=1,
                    label=keys[element])
            plt.legend(loc='upper left')
            plt.title('SWU: cumulative')
            plt.xlabel('time [months]')
            plt.ylabel('SWU')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()

        else:

            limit = 10**25
            for element in range(len(keys)):
                swu = np.array(swu_dict[keys[element]])
                swu[swu > limit] = np.nan
                swu[swu == 0] = np.nan
                plt.plot(
                    swu,
                    linestyle=' ',
                    marker='.',
                    markersize=1,
                    label=keys[element])
            plt.legend(loc='upper left')
            plt.title('SWU: noncumulative')
            plt.xlabel('time [months]')
            plt.ylabel('SWU')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()


def plot_power_ot(cur, is_cum=True, is_tot=False):
    """
    Function creates a dictionary of power from each reactor over time, then plots it
    according to the options set by the user when the function is called.

    Inputs:
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Outputs:
    none, but it shows the power plot.

    """

    # This function does exactly what plot swu does, but it uses the data
    # pulled from timeseriespower instead.
    power_dict = {}
    agentid = get_agent_ids(cur, 'Reactor')
    init_year, init_month, duration, timestep = get_timesteps(cur)

    for num in agentid:
        power_data = cur.execute('SELECT time, value '
                                 'FROM timeseriespower '
                                 'WHERE agentid = ' + str(num)).fetchall()
        if is_cum:
            power_timeseries = get_timeseries_cum(power_data, duration, False)
        else:
            power_timeseries = get_timeseries(power_data, duration, False)

        power_dict['Reactor_' + str(num)] = power_timeseries

    keys = []
    for key in power_dict.keys():
        keys.append(key)

    if len(power_dict) == 1:

        if is_cum:

            plt.plot(power_dict[keys[0]], linestyle='-', linewidth=1)
            plt.title('Power: cumulative')
            plt.xlabel('time [months]')
            plt.ylabel('power [MWe]')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()

        else:

            power = np.array(power_dict[keys[0]])

            power[power == 0] = np.nan
            plt.plot(power, linestyle=' ', marker='.', markersize=1)
            plt.title('Power: noncumulative')
            plt.xlabel('time [months]')
            plt.ylabel('power [MWe]')
            plt.xlim(left=0.0)
            plt.ylim(bottom=0.0)
            plt.show()

    else:

        if is_cum:
            if not is_tot:

                for element in range(len(keys)):
                    plt.plot(
                        power_dict[
                            keys[element]],
                        linestyle='-',
                        linewidth=1,
                        label=keys[element])
                plt.legend(loc='upper left')
                plt.title('Power: cumulative')
                plt.xlabel('time [months]')
                plt.ylabel('power [MWe]')
                plt.xlim(left=0.0)
                plt.ylim(bottom=0.0)
                plt.show()

            else:
                total_power = np.zeros(len(power_dict[keys[0]]))
                for element in range(len(keys)):
                    for index in range(len(power_dict[keys[0]])):
                        total_power[index] += power_dict[keys[element]][index]

                plt.plot(total_power, linestyle='-', linewidth=1)
                plt.title('Total Power: cumulative')
                plt.xlabel('time [months]')
                plt.ylabel('power [MWe]')
                plt.xlim(left=0.0)
                plt.ylim(bottom=0.0)
                plt.show()

        else:
            if not is_tot:

                for element in range(len(keys)):
                    power = np.array(power_dict[keys[element]])
                    power[power == 0] = np.nan
                    plt.plot(
                        power,
                        linestyle=' ',
                        marker='.',
                        markersize=1,
                        label=keys[element])
                plt.legend(loc='lower left')
                plt.title('Power: noncumulative')
                plt.xlabel('time [months]')
                plt.ylabel('power [MWe]')
                plt.xlim(left=0.0)
                plt.ylim(bottom=0.0)
                plt.show()

            else:

                total_power = np.zeros(len(power_dict[keys[0]]))
                for element in range(len(keys)):
                    for index in range(len(power_dict[keys[0]])):
                        total_power[index] += power_dict[keys[element]][index]

                total_power[total_power == 0] = np.nan
                plt.plot(total_power, linestyle=' ', marker='.', markersize=1)
                plt.title('Total Power: noncumulative')
                plt.xlabel('time [months]')
                plt.ylabel('power [MWe]')
                plt.xlim(left=0.0)
                plt.ylim(bottom=0.0)
                plt.show()


# some functions pulled from analysis.py

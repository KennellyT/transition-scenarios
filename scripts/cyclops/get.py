import collections
import numpy as np
import matplotlib.pyplot as plt
import sqlite3 as lite
import sys
from itertools import cycle
import matplotlib
from matplotlib import cm
from pyne import nucname
import cyanalysis
import cywrite
import cy_plots_math
import cyclops


def get_cursor(file_name):
    """Connects and returns a cursor to an sqlite output file

    Parameters
    ----------
    file_name: str
        name of the sqlite file

    Returns
    -------
    sqlite cursor3
    """
    con = lite.connect(file_name)
    con.row_factory = lite.Row
    return con.cursor()


def get_agent_ids(cur, archetype):
    """Gets all agentIds from Agententry table for wanted archetype

        agententry table has the following format:
            SimId / AgentId / Kind / Spec /
            Prototype / ParentID / Lifetime / EnterTime

    Parameters
    ----------
    cur: cursor
        sqlite cursor3
    archetype: str
        agent's archetype specification

    Returns
    -------
    id_list: list
        list of all agentId strings
    """
    agents = cur.execute("SELECT agentid FROM agententry WHERE spec "
                         "LIKE '%" + archetype + "%' COLLATE NOCASE"
                         ).fetchall()

    return list(str(agent['agentid']) for agent in agents)


def get_prototype_id(cur, prototype):
    """Returns agentid of a prototype

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    prototype: str
        name of prototype

    Returns
    -------
    agent_id: list
        list of prototype agent_ids as strings
    """
    ids = cur.execute('SELECT agentid FROM agententry '
                      'WHERE prototype = "' +
                      str(prototype) + '" COLLATE NOCASE').fetchall()

    return list(str(agent['agentid']) for agent in ids)


def get_inst(cur):
    """Returns prototype and agentids of institutions

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    -------
    sqlite query result (list of tuples)
    """
    return cur.execute('SELECT prototype, agentid FROM agententry '
                       'WHERE kind = "Inst"').fetchall()


def timestep_to_years(init_year, timestep):
    """Returns list of years in simulation

    Parameters
    ----------
    init_year: int
        initial year in simulation
    timestep: np.array
        timestep of simulation (months)

    Returns
    -------
    array of years
    """

    return init_year + (timestep / 12)


def get_timesteps(cur):
    """Returns simulation start year, month, duration and
    timesteps (in numpy linspace).

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    -------
    init_year: int
        start year of simulation
    init_month: int
        start month of simulation
    duration: int
        duration of simulation
    timestep: list
        linspace up to duration
    """
    info = cur.execute('SELECT initialyear, initialmonth, '
                       'duration FROM info').fetchone()
    init_year = info['initialyear']
    init_month = info['initialmonth']
    duration = info['duration']
    timestep = np.linspace(0, duration - 1, num=duration)

    return init_year, init_month, duration, timestep


def get_timeseries(in_list, duration, kg_to_tons):
    """returns a timeseries list from in_list data.

    Parameters
    ----------
    in_list: list
        list of data to be created into timeseries
        list[0] = time
        list[1] = value, quantity
    duration: int
        duration of the simulation
    kg_to_tons: bool
        if True, list returned has units of tons
        if False, list returned as units of kilograms

    Returns
    -------
    timeseries list of commodities stored in in_list
    """
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
    """returns a timeseries list from in_list data.

    Parameters
    ----------
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

    Returns
    -------
    timeseries of commodities in kg or tons
    """
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


def get_isotope_transactions(resources, compositions):
    """Creates a dictionary with isotope name, mass, and time

    Parameters
    ----------
    resources: list of tuples
        resource data from the resources table
        (times, sum(quantity), qualid)
    compositions: list of tuples
        composition data from the compositions table
        (qualid, nucid, massfrac)

    Returns
    -------
    transactions: dictionary
        dictionary with "key=isotope, and
        value=list of tuples (time, mass_moved)"
    """
    transactions = collections.defaultdict(list)
    for res in resources:
        for comp in compositions:
            if res['qualid'] == comp['qualid']:
                transactions[comp['nucid']].append((res['time'],
                                                    res['sum(quantity)'] *
                                                    comp['massfrac']))

    return transactions


def get_stockpile(cur, facility, is_cum=True):
    """gets inventory timeseries in a fuel facility

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    facility: str
        name of facility
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns
    -------
    pile_dict: dictionary
        dictionary with "key=agent type, and
        value=timeseries list of stockpile"
    """
    pile_dict = collections.OrderedDict()
    agentid = get_agent_ids(cur, facility)
    query = exec_string(agentid, 'agentid', 'timecreated, quantity, qualid')
    query = query.replace('transactions', 'agentstateinventories')
    stockpile = cur.execute(query).fetchall()
    init_year, init_month, duration, timestep = get_timesteps(cur)
    if is_cum:
        stock_timeseries = get_timeseries_cum(stockpile, duration, True)
    else:
        stock_timeseries = get_timeseries(stockpile, duration, True)
    pile_dict[facility] = stock_timeseries

    return pile_dict


def get_swu_dict(cur, is_cum=True):
    """returns dictionary of swu timeseries for each enrichment plant

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns
    -------
    swu_dict: dictionary
        dictionary with "key=Enrichment (facility number), and
        value=swu timeseries list"
    """
    swu_dict = collections.OrderedDict()
    agentid = get_agent_ids(cur, 'Enrichment')
    init_year, init_month, duration, timestep = get_timesteps(cur)
    for num in agentid:
        swu_data = cur.execute('SELECT time, value '
                               'FROM timeseriesenrichmentswu '
                               'WHERE agentid = ' + str(num)).fetchall()
        if is_cum:
            swu_timeseries = get_timeseries_cum(swu_data, duration, False)
        else:
            swu_timeseries = get_timeseries(swu_data, duration, False)

        swu_dict['Enrichment_' + str(num)] = swu_timeseries

    return swu_dict


def get_power_dict(cur):
    """Gets dictionary of power capacity by calling capacity_calc

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    ------
    power_dict: dictionary
        "dictionary with key=government, and
        value=timeseries list of installed capacity"
    """
    init_year, init_month, duration, timestep = get_timesteps(cur)
    governments = get_inst(cur)

    # get power cap values
    entry_exit = cur.execute('SELECT max(value), timeseriespower.agentid, '
                             'parentid, entertime, entertime + lifetime'
                             ' FROM agententry '
                             'INNER JOIN timeseriespower '
                             'ON agententry.agentid = timeseriespower.agentid '
                             'GROUP BY timeseriespower.agentid').fetchall()

    return capacity_calc(governments, timestep, entry_exit)


def get_power_dict_of_region(cur, region_name):
    """Gets dictionary of power capacity of a specific region

    Parameters
    ----------
    cur: sqlite cursor
    region_name: str
        name of region to serach for

    Returns
    -------
    power_dict: dictionary
        "dictionary with key=government and
        value=timeseries list of installed capacity"
    """
    parentid = cur.exectue('SELECT agentid FROM agententry WHERE '
                           'Prototype LIKE "%' + region_name + '%" '
                           'AND Kind = "Inst"').fetchone()

    entry_exit = cur.execute('SELECT max(value), timeseriespower.agentid, '
                             'parentid, entrytime, entertime + lifetime'
                             ' FROM agententry '
                             'INNER JOIN timeseriespower '
                             'ON agententry.agentid = timeseriespower.agentid '
                             'GROUP BY timeseriespower.agentid '
                             'WHERE parentid = %i' % parentid[0]).fetchall()


def get_deployment_dict(cur):
    """Gets dictionary of reactors deployed over time
    by calling reactor_deployments

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    ------
    num_dict: dictionary
        "dictionary with key=government, and
        value=timeseries list of number of reactors"
    """
    init_year, init_month, duration, timestep = get_timesteps(cur)
    governments = get_inst(cur)

    # get power cap values
    entry = cur.execute('SELECT max(value), timeseriespower.agentid, '
                        'parentid, entertime FROM agententry '
                        'INNER JOIN timeseriespower '
                        'ON agententry.agentid = timeseriespower.agentid '
                        'GROUP BY timeseriespower.agentid').fetchall()

    exit_step = cur.execute('SELECT max(value), timeseriespower.agentid, '
                            'parentid, exittime FROM agentexit '
                            'INNER JOIN timeseriespower '
                            'ON agentexit.agentid = timeseriespower.agentid'
                            ' INNER JOIN agententry '
                            'ON agentexit.agentid = agententry.agentid '
                            'GROUP BY timeseriespower.agentid').fetchall()
    return reactor_deployments(governments, timestep, entry, exit_step)


def trade_timeseries(cur, sender, receiver,
                   is_prototype, do_isotopic,
                   is_cum=True):
    """Returns trade timeseries between two prototypes' or facilities
    with or without isotopics

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    sender: str
        name of sender as facility type or prototype name
    receiver: str
        name of receiver as facility type or prototype name
    is_prototype: bool
        if True, search sender and receiver as prototype,
        if False, as facility type from spec.
    do_isotopic: bool
        if True, perform isotopics (takes significantly longer)
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns:
    --------
    trades: dictionary
        if do_isotopic:
            dictionary with "key=isotope, and
                        value=timeseries list
                        of mass traded between
                        two prototypes"
        else:
            dictionary with "key=string, sender to receiver,
                        value=timeseries list of mass traded
                        between two prototypes"

    """
    init_year, init_month, duration, timestep = get_timesteps(cur)
    isotope_timeseries = collections.defaultdict(list)
    trades = collections.defaultdict()

    if is_prototype:
        sender_id = get_prototype_id(cur, sender)
        receiver_id = get_prototype_id(cur, receiver)
    else:
        sender_id = get_agent_ids(cur, sender)
        receiver_id = get_agent_ids(cur, receiver)

    if do_isotopic:
        trade = cur.execute('SELECT time, sum(quantity)*massfrac, nucid '
                            'FROM transactions INNER JOIN resources ON '
                            'resources.resourceid = transactions.resourceid '
                            'LEFT OUTER JOIN compositions '
                            'ON compositions.qualid = resources.qualid '
                            'WHERE (senderid = ' +
                            ' OR senderid = '.join(sender_id) +
                            ') AND (receiverid = ' +
                            ' OR receiverid = '.join(receiver_id) +
                            ') GROUP BY time, nucid').fetchall()
    else:
        trade = cur.execute('SELECT time, sum(quantity), qualid '
                            'FROM transactions INNER JOIN resources ON '
                            'resources.resourceid = transactions.resourceid'
                            ' WHERE (senderid = ' +
                            ' OR senderid = '.join(sender_id) +
                            ') AND (receiverid = ' +
                            ' OR receiverid = '.join(receiver_id) +
                            ') GROUP BY time').fetchall(
        )
    if do_isotopic:
        for time, amount, nucid in trade:
            isotope_timeseries[nucname.name(nucid)].append((time, amount))
        for key in isotope_timeseries:
            if is_cum:
                isotope_timeseries[key] = get_timeseries_cum(
                    isotope_timeseries[key], duration, True)
            else:
                isotope_timeseries[key] = get_timeseries(isotope_timeseries[key], duration, True)
        return isotope_timeseries
    else:
        key_name = str(sender)[:5] + ' to ' + str(receiver)[:5]
        if is_cum:
            trades[key_name] = get_timeseries_cum(trade, duration, True)
        else:
            trades[key_name] = get_timeseries(trade, duration, True)
        return trades



def get_waste_dict(isotope_list, mass_list, time_list, duration):
    """Given an isotope, mass and time list, creates a dictionary
       With key as isotope and time series of the isotope mass.

    Parameters
    ----------
    isotope_list: list
        list with all the isotopes from resources table
    mass_list: list
        list with all the mass values from resources table
    time_list: list
        list with all the time values from resources table
    duration: int
        simulation duration

    Returns
    -------
    waste_dict: dictionary
        dictionary with "key=isotope, and
        value=mass timeseries of each unique isotope"
    """
    waste_dict = collections.OrderedDict()
    isotope_set = set(isotope_list)
    for iso in isotope_set:
        mass = 0
        time_mass = []
        # at each timestep,
        for i in range(0, duration):
            # for each element in database,
            for x, y in enumerate(isotope_list):
                if i == time_list[x] and y == iso:
                    mass += mass_list[x]
            time_mass.append(mass)
        waste_dict[iso] = time_mass

    return waste_dict

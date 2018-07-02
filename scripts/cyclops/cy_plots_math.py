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
import cyclops


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


def fuel_usage_timeseries(cur, fuels, is_cum=True):
    """Calculates total fuel usage over time

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    fuels: list
        list of fuel commodity names (eg. uox, mox) as string
        to consider in fuel usage.
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns
    -------
    fuel_timeseries: dictionary
        dictionary with "key=fuel (from fuels),
        value=timeseries list of fuel amount [kg]"
    """
    fuel_timeseries = collections.OrderedDict()
    init_year, init_month, duration, timestep = get_timesteps(cur)
    for fuel in fuels:
        temp_list = [fuel]
        fuel_quantity = cur.execute(exec_string(temp_list, 'commodity',
                                                'time, sum(quantity)') +
                                    ' GROUP BY time').fetchall()
        quantity_timeseries = []
        try:
            if is_cum:
                quantity_timeseries = get_timeseries_cum(
                    fuel_quantity, duration, True)
            else:
                quantity_timeseries = get_timeseries(
                    fuel_quantity, duration, True)
            fuel_timeseries[fuel] = quantity_timeseries
        except:
            print(str(fuel) + ' has not been used.')

    return fuel_timeseries



def nat_u_timeseries(cur, is_cum=True):
    """Finds natural uranium supply from source
        Since currently the source supplies all its capacity,
        the timeseriesenrichmentfeed is used.

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns
    -------
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


def final_stockpile(cur, facility):
    """get final stockpile in a fuel facility

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    facility: str
        name of facility

    Returns
    -------
    mthm_stockpile: str
        MTHM value of stockpile
    """
    agentid = get_agent_ids(cur, facility)
    mthm_stockpile = ''
    for agent in agentid:
        count = 1
        name = cur.execute('SELECT prototype FROM agententry'
                           'WHERE agentid = ' + str(agent)).fetchone()

        mthm_stockpile += 'The Stockpile in ' + str(name[0]) + ' : \n \n'
        stkpile = cur.execute('SELECT sum(quantity), inventoryname, qualid'
                              ' FROM agentstateinventories'
                              ' INNER JOIN resources'
                              ' ON resources.resourceid'
                              ' = agentstateinventories.resourceid'
                              ' WHERE agentstateinventories.agentid'
                              ' = """ + str(agent) + """ GROUP BY'
                              ' inventoryname').fetchall()
        for stream in stkpile:
            masses = cur.execute('SELECT qualid, nucid, massfrac '
                                 'FROM compositions '
                                 'WHERE qualid = ' +
                                 str(stream['qualid'])).fetchall()

            mthm_stockpile += ('Stream ' + str(count) +
                          ' Total = ' + str(stream['sum(quantity)']) +
                          ' kg \n')
            for isotope in masses:
                mthm_stockpile += (str(isotope['nucid']) + ' = ' +
                              str(isotope['massfrac'] *
                                  stream['sum(quantity)']) +
                              ' kg \n')
            mthm_stockpile += '\n'
            count += 1
        mthm_stockpile += '\n'
    mthm_stockpile += '\n'

    return mthm_stockpile



def fuel_into_reactors(cur, is_cum=True):
    """Finds timeseries of mass of fuel received by reactors

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    is_cum: bool
        gets cumulative timeseris if True, monthly value if False

    Returns
    -------
    timeseries list of fuel into reactors [tons]
    """
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


def u_util_calc(cur):
    """Returns fuel utilization factor of fuel cycle

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    -------
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

    return u_util_timeseries


def multiple_line_plots(dictionary, timestep,
                        xlabel, ylabel, title,
                        outputname, init_year):
    """Creates multiple line plots of timestep vs dictionary

    Parameters
    ----------
    dictionary: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    timestep: numpy linspace
        timestep of simulation
    xlabel: str
        xlabel of plot
    ylabel: str
        ylabel of plot
    title: str
        title of plot
    init_year: int
        initial year of simulation

    Returns
    -------
    """
    # set different colors for each bar
    color_index = 0
    # for every country, create bar chart with different color
    for key in dictionary:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)

        plt.plot(timestep_to_years(init_year, timestep),
                 dictionary[key],
                 label=label)
        color_index += 1
        if sum(sum(dictionary[k]) for k in dictionary) > 1000:
            ax = plt.gca()
            ax.get_yaxis().set_major_formatter(
                plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
        plt.ylabel(ylabel)
        plt.title(title)
        plt.xlabel(xlabel)
        plt.legend(loc=(1.0, 0), prop={'size': 10})
        plt.grid(True)
        plt.savefig(label + '_' + outputname + '.png',
                    format='png',
                    bbox_inches='tight')
        plt.close()


def combined_line_plot(dictionary, timestep,
                       xlabel, ylabel, title,
                       outputname, init_year):
    """Creates a combined line plot of timestep vs dictionary

    Parameters
    ----------
    dictionary: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    timestep: numpy linspace
        timestep of simulation
    xlabel: str
        xlabel of plot
    ylabel: str
        ylabel of plot
    title: str
        title of plot
    init_year: int
        initial year of simulation

    Returns
    -------
    """
    # set different colors for each bar
    color_index = 0
    plt.figure()
    # for every country, create bar chart with different color
    for key in dictionary:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)

        plt.plot(timestep_to_years(init_year, timestep),
                 dictionary[key],
                 label=label,
                 color=cm.viridis(float(color_index) / len(dictionary)))
        color_index += 1

    if sum(sum(dictionary[k]) for k in dictionary) > 1000:
        ax = plt.gca()
        ax.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.legend(loc=(1.0, 0), prop={'size': 10})
    plt.grid(True)
    plt.savefig(label + '_' + outputname + '.png',
                format='png',
                bbox_inches='tight')
    plt.close()


def double_axis_bar_line_plot(dictionary1, dictionary2, timestep,
                              xlabel, ylabel1, ylabel2,
                              title, outputname, init_year):
    """Creates a double-axis plot of timestep vs dictionary

    It is recommended that a non-cumulative timeseries is on dictionary1.

    Parameters
    ----------
    dictionary1: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    dictionary2: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    timestep: numpy linspace
        timestep of simulation
    xlabel: str
        xlabel of plot
    ylabel: str
        ylabel of plot
    title: str
        title of plot
    init_year: int
        initial year of simulation

    Returns
    -------
    """
    # set different colors for each bar

    fig, ax1 = plt.subplots()
    # for every country, create bar chart with different color
    color1 = 'r'
    color2 = 'b'
    for key in dictionary1:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)
        if sum(dictionary1[key]) == 0:
            print(label + ' has no values')
        else:
            ax1.bar(timestep_to_years(init_year, timestep),
                    dictionary1[key],
                    label=label,
                    color=color1)
    ax1.set_xlabel(xlabel)
    ax1.set_ylabel(ylabel1, color=color1)
    ax1.tick_params('y', colors=color1)
    if sum(sum(dictionary1[k]) for k in dictionary1) > 1000:
        ax1 = plt.gca()
        ax1.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    ax2 = ax1.twinx()

    lines = ['-', '--', '-.', ':']
    linecycler = cycle(lines)
    for key in dictionary2:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)

        if sum(dictionary2[key]) == 0:
            print(label + ' has no values')
        else:
            ax2.plot(timestep_to_years(init_year, timestep),
                     dictionary2[key],
                     label=label,
                     color=color2,
                     linestyle=next(linecycler))
    ax2.set_ylabel(ylabel2, color=color2)
    ax2.tick_params('y', colors=color2)

    if sum(sum(dictionary2[k]) for k in dictionary2) > 1000:
        ax2 = plt.gca()
        ax2.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))

    plt.title(title)
    plt.grid(True)
    plt.savefig(label + '_' + outputname + '.png',
                format='png',
                bbox_inches='tight')
    plt.close()


def double_axis_line_line_plot(dictionary1, dictionary2, timestep,
                               xlabel, ylabel1, ylabel2,
                               title, outputname, init_year):
    """Creates a double-axis plot of timestep vs dictionary

    Parameters
    ----------
    dictionary1: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    dictionary2: dictionary
        dictionary with "key=description of timestep, and
        value=list of timestep progressions"
    timestep: numpy linspace
        timestep of simulation
    xlabel: str
        xlabel of plot
    ylabel: str
        ylabel of plot
    title: str
        title of plot
    init_year: int
        initial year of simulation

    Returns
    -------
    """
    # set different colors for each bar
    lines = ['-', '--', '-.', ':']
    linecycler = cycle(lines)
    fig, ax1 = plt.subplots()
    top = True
    color1 = 'r'
    color2 = 'b'
    # for every country, create bar chart with different color
    for key in dictionary1:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)
        if top:
            lns = ax1.plot(timestep_to_years(init_year, timestep),
                           dictionary1[key],
                           label=label,
                           color=color1,
                           linestyle=next(linecycler))
            top = False
        else:
            lns += ax1.plot(timestep_to_years(init_year, timestep),
                            dictionary1[key],
                            label=label,
                            color=color1,
                            linestyle=next(linecycler))
    ax1.set_xlabel(xlabel)
    ax1.set_ylabel(ylabel1, color=color1)
    ax1.tick_params('y', colors=color1)
    if sum(sum(dictionary1[k]) for k in dictionary1) > 1000:
        ax1 = plt.gca()
        ax1.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    ax2 = ax1.twinx()

    linecycler = cycle(lines)

    for key in dictionary2:
        # label is the name of the nuclide (converted from ZZAAA0000 format)
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)

        lns += ax2.plot(timestep_to_years(init_year, timestep),
                        dictionary2[key],
                        label=label,
                        color=color2,
                        linestyle=next(linecycler))
    ax2.set_ylabel(ylabel2, color=color2)
    ax2.tick_params('y', colors=color2)

    if sum(sum(dictionary2[k]) for k in dictionary2) > 1000:
        ax2 = plt.gca()
        ax2.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))

    plt.title(title)
    labs = [l.get_label() for l in lns]
    plt.legend(lns, labs, loc=0, prop={'size': 10})
    plt.grid(True)
    plt.savefig(label + '_' + outputname + '.png',
                format='png',
                bbox_inches='tight')
    plt.close()


def stacked_bar_chart(dictionary, timestep,
                      xlabel, ylabel, title,
                      outputname, init_year):
    """Creates stacked bar chart of timstep vs dictionary

    Parameters
    ----------
    dictionary: dictionary
        dictionary with value: timeseries data
    timestep: numpy linspace
        list of timestep (x axis)
    xlabel: str
        xlabel of plot
    ylabel: str
        ylabel of plot
    title: str
        title of plot
    init_year: int
        simulation start year

    Returns
    -------
    """
    # set different colors for each bar
    color_index = 0
    top_index = True
    prev = np.zeros(1)
    plot_list = []
    # for every country, create bar chart with different color
    for key in dictionary:
        if isinstance(key, str) is True:
            label = key.replace('_government', '')
        else:
            label = str(key)
        # very first country does not have a 'bottom' argument
        if sum(dictionary[key]) == 0:
            print(label + ' has no values')
        elif top_index is True:
            plot = plt.bar(x=timestep_to_years(init_year, timestep),
                           height=dictionary[key],
                           width=0.5,
                           color=cm.viridis(
                float(color_index) / len(dictionary)),
                edgecolor='none',
                label=label)
            prev = dictionary[key]
            top_index = False
            plot_list.append(plot)

        # All curves except the first have a 'bottom'
        # defined by the previous curve
        else:
            plot = plt.bar(x=timestep_to_years(init_year, timestep),
                           height=dictionary[key],
                           width=0.5,
                           color=cm.viridis(
                float(color_index) / len(dictionary)),
                edgecolor='none',
                bottom=prev,
                label=label)
            prev = np.add(prev, dictionary[key])
            plot_list.append(plot)

        color_index += 1

    # plot
    if sum(sum(dictionary[k]) for k in dictionary) > 1000:
        ax = plt.gca()
        ax.get_yaxis().set_major_formatter(
            plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    plt.ylabel(ylabel)
    plt.title(title)
    plt.xlabel(xlabel)
    axes = plt.gca()
    if len(dictionary) > 1:
        plt.legend(loc=(1.0, 0))
    plt.grid(True)
    plt.savefig(outputname + '.png', format='png', bbox_inches='tight')
    plt.close()


def plot_power(cur):
    """Gets capacity vs time for every country
        in stacked bar chart.

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor

    Returns
    -------
    """
    init_year, init_month, duration, timestep = get_timesteps(cur)
    power_dict = get_power_dict(cur)
    stacked_bar_chart(power_dict, timestep,
                      'Years', 'Net_Capacity [GWe]',
                      'Net Capacity vs Time',
                      'power_plot', init_year)

    deployment_dict = get_deployment_dict(cur)
    stacked_bar_chart(deployment_dict, timestep,
                      'Years', 'Number of Reactors',
                      'Number of Reactors vs Time',
                      'num_plot', init_year)


def plot_in_out_flux(cur, facility, influx_bool, title, outputname):
    """plots timeseries influx/ outflux from facility name in kg.

    Parameters
    ----------
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

    Returns
    -------
    """
    agent_ids = get_agent_ids(cur, facility)
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

    compositions = cur.execute('SELECT qualid, nucid, massfrac '
                               'FROM compositions').fetchall()

    init_year, init_month, duration, timestep = get_timesteps(cur)
    transactions = get_isotope_transactions(resources, compositions)
    waste_dict = get_waste_dict(transactions.keys(),
                                transactions.values()[0],
                                transactions.values()[1],
                                duration)

    if influx_bool is False:
        stacked_bar_chart(waste_dict, timestep,
                          'Years', 'Mass [kg]',
                          title, outputname, init_year)
    else:
        multi_line_plot(waste_dict, timestep,
                        'Years', 'Mass [kg]',
                        title, outputname, init_year)


def source_throughput(cur, duration, frac_prod, frac_tail):
    """Calculates throughput required for nat_u source before enrichment
    by calculating the average mass of fuel gone into reactors over
    simulation. Assuming natural uranium is put as feed

    Parameters
    ----------
    cur: sqlite cursor
        sqlite cursor
    duration: int
        duration of simulation
    frac_prod: float
        mass fraction of U235 in fuel after enrichment in decimals
    frac_tail: float
        mass fraction of U235 in tailings after enrichment in decimals

    Returns
    -------
    throughput: float
        appropriate nat_u throughput for source
    """
    avg_fuel_used = fuel_into_reactors(cur)[-1] * 1000 / duration
    feed_factor = (frac_prod - frac_tail) / (0.00711 - frac_tail)
    print('Throughput should be at least: ' +
          str(feed_factor * avg_fuel_used) + ' [kg]')
    return feed_factor * avg_fuel_used

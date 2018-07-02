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


def write_csv(header, raw_input, filename='csv-data.csv'):
    """
    ***Warning!  This function will check to see if there is already a file 'filename' in the current directory,
    and if one is found it will be deleted.  Please be aware of this when choosing file names.***

    Function will write a csv file given the header, data, and the desired name of the csv file
    to be made.

    Input:
    header: a list, all strings, of the headers for the csv file
    data_input: data to be added to csv file - see note below
    filename: optional - the desired output file name, default: 'csv-data.csv'

    Output:
    none in the script, but in your working directory, you should find the file

    note:  this function expects raw data in the form of [[a1, a2, ... , aN],[b1, b2, ... ,bN]...[n1, n2, nN]],
            but it will put this data in the form of [[a1,b1,...,n1],[a2,b2,...,n2],...,[aN,bN,...,nN]] before
            writing it to the csv file.  Additionally, please be sure that the order of data in the raw input
            matches the order of headers.  Using the previous example of an arbitrary raw input, the header
            should be: ['header a','header b',...,'header n'].

    """

    # checks to see if the file "filename" already exists in the current directory.  If it does,
    # it is deleted.
    if os.path.exists('./' + filename) is True:
        os.remove(filename)

    # next, it checks to see if the raw data is a series of lists, or just one set of data.
    # if the raw input is a series of lists, it is first re-organized into a list of lists where each
    # element contains the data of a single reactor.
    if isinstance(raw_input[0], list):

        data_input = []

        for element in range(len(raw_input[0])):
            data_input.append([])

        for element in range(len(raw_input[0])):
            for index in range(len(raw_input)):
                placeholder = raw_input[index]
                data_input[element].append(placeholder[element])

        # once it is in the right format, it is written to the csv file.
        with open(filename, 'a+') as file:
            w = csv.writer(file)
            w.writerow(header)
            for element in range(len(data_input)):
                w.writerow(data_input[element])

    # if the first element was not a list, it means the raw input contains the data for only
    # one reactor, and does not need to be reorganized.  Instead, the raw input is directly written
    # to the csv file.
    else:
        with open(filename, 'a+') as file:
            w = csv.writer(file)
            w.writerow(header)
            w.writerow(raw_input)


def recipe_dict(fresh_id, fresh_comp, spent_id, spent_comp):
    """
    Function takes recipes for fresh and spent fuel, split into lists of isotope names and compostions, and
    organizes them into a dictionary in the key:value format

    Input:
    fresh_id: isotope names in fresh fuel
    fresh_comp: isotope compositions in fresh fuel
    spent_id: isotope compostions in spent fuel
    spent_id: isotope compostions in spent fuel

    note:  the overall isotope order doesn't matter, or their number, but the order of isotopes
    in the id list should be the same as the isotope order in the corresponding compostion list.

    Output:
    fresh: key:value fresh recipe format
    spent: key:value spent recipe format

    """

    # first, the function checks that the id lists and composition lists are
    # equal in length
    assert len(fresh_id) == len(
        fresh_comp), 'The lengths of fresh_id and fresh_comp are not equal'
    assert len(spent_id) == len(
        spent_comp), 'The lengths of spent_id and spent_comp are not equal'

    # next, the function creates an empty dictionary object (note the curly brackets, {})
    # and then uses a loop to create each element of the dictionary, matching the first
    # element of the id list with the first element of the composition list.  If you
    # are unfamiliar with dictionary objects, a quick note: dictionaries cannot
    # use .append() as an array or list could.  Instead, this function uses
    # .update()
    fresh = {}
    for element in range(len(fresh_id)):
        fresh.update({fresh_id[element]: fresh_comp[element]})

    spent = {}
    for element in range(len(spent_id)):
        spent.update({spent_id[element]: spent_comp[element]})

    return fresh, spent


def load_template(template):
    """
    Function reads a jinja2 template.

    Input:
    template: filename of the desired jinja2 template

    Output:  jinja2 template
    """

    # this function only really has one step, which is to read the desired jinja2 template
    # from file and return it.  This function doesn't really get used on its own, rather,
    # it is called from within functions that render portions of the Cyclus
    # input file.
    with open(template, 'r') as input_template:
        output_template = jinja2.Template(input_template.read())

    return output_template


def write_reactor(
        reactor_data,
        reactor_template,
        output_name='rendered-reactor.xml'):
    """

    ***Warning!  This function will check to see if there is already a file 'output_name' in the current directory,
    and if one is found it will be deleted.  Please be aware of this when choosing file names.***

    Function renders the reactor portion of the Cyclus input file.

    Input:
    reactor_data: the reactor data, as a pandas dataframe
    reactor_template: name of reactor template file
    output_name: filename of rendered reactor input - default: 'rendered-reactor.xml'

    Output:
    rendered reactor input filename

    """

    # first, it will check to see if the file named by output_name exists, and
    # if it does, deletes it
    if os.path.exists('./' + output_name) is True:
        os.remove(output_name)

    # then, the previously defined load_template function is used to get the
    # jinja2 template.
    template = load_template(reactor_template)

    # This step is a quick example of how one might specify and input the specifications of
    # certain reactor types.  Here, PWR and BWRs are used, but this could be done with any current
    # reactor model, provided you have all the relevant information.  This function will also
    # run if you input a reactor type not listed, but it prints a warning and just uses PWR
    # specs.

    # assem_size is the weight of the assembly in kg, n_assem_core is the number of assemblies
    # per core, and n_assem_batch is the number of assemblies per batch.  For more information about
    # Cycamore archetypes and the input variables in them, go to
    # http://fuelcycle.org/user/cycamoreagents.html#cycamore-reactor
    PWR_cond = {'assem_size': 33000, 'n_assem_core': 3, 'n_assem_batch': 1}

    BWR_cond = {'assem_size': 33000, 'n_assem_core': 3, 'n_assem_batch': 1}
    # ask about these values later, I think the tutorial assumes the core is in three big pieces,
    # and so it divides the weight of the (fuel? total assemblies?) by 3

    reactor_data = reactor_data.drop(['Country', 'Operator'], 'columns')
    reactor_data = reactor_data.drop_duplicates()

    # first, the function checks if it is dealing with data for a single
    # reactor, or multiple reactors.
    if len(reactor_data) == 1:

        # these are the steps for a single reactor input.  There is only one element in the
        # reactor data list, so '0' can be used in .iloc
        # if you are unfamiliar with dataframes, and .iloc and loc, it may be helpful to look
        # up the documentation.  In brief, .iloc can index the data frame using integer, postion-based
        # indexing, or a boolean array.  .loc, on the other hand, uses labels.  Notice that the labels
        # .loc accepts are the same as our header - this is not coincidence.

        # this first checks for the type of reactor, and renders the correct information based on the
        # reactor type.
        if reactor_data.iloc[0, :].loc['Type'] == 'PWR':
            reactor_body = template.render(
                reactor_name=reactor_data.iloc[0, :].loc['Reactor Name'],
                assem_size=PWR_cond['assem_size'],
                n_assem_core=PWR_cond['n_assem_core'],
                n_assem_batch=PWR_cond['n_assem_batch'],
                capacity=reactor_data.iloc[0, :].loc['Net Electric Capacity'])

            with open(output_name, 'a+') as output:
                output.write(reactor_body)

        elif reactor_data.iloc[0, :].loc['Type'] == 'BWR':
            reactor_body = template.render(
                reactor_name=reactor_data.iloc[0, :].loc['Reactor Name'],
                assem_size=BWR_cond['assem_size'],
                n_assem_core=BWR_cond['n_assem_core'],
                n_assem_batch=BWR_cond['n_assem_batch'],
                capacity=reactor_data.iloc[0, :].loc['Net Electric Capacity'])

            with open(output_name, 'a+') as output:
                output.write(reactor_body)

        else:
            print(
                'Warning: specifications of this reactor type have not been given.  Using placeholder values.')

            reactor_body = template.render(
                reactor_name=reactor_data.iloc[0, :].loc['Reactor Name'],
                assem_size=PWR_cond['assem_size'],
                n_assem_core=PWR_cond['n_assem_core'],
                n_assem_batch=PWR_cond['n_assem_batch'],
                capacity=reactor_data.iloc[0, :].loc['Net Electric Capacity'])

            with open(output_name, 'a+') as output:
                output.write(reactor_body)

    else:

        # This does what the above if statement does, with an added for loop to
        # accommodate data for multiple reactors.
        for element in range(len(reactor_data)):

            if reactor_data.iloc[element, :].loc['Type'] == 'PWR':
                reactor_body = template.render(
                    reactor_name=reactor_data.iloc[
                        element,
                        :].loc['Reactor Name'],
                    assem_size=PWR_cond['assem_size'],
                    n_assem_core=PWR_cond['n_assem_core'],
                    n_assem_batch=PWR_cond['n_assem_batch'],
                    capacity=reactor_data.iloc[
                        element,
                        :].loc['Net Electric Capacity'])

                with open(output_name, 'a+') as output:
                    output.write(reactor_body + "\n \n")

            elif reactor_data.iloc[element, :].loc['Type'] == 'BWR':
                reactor_body = template.render(
                    reactor_name=reactor_data.iloc[
                        element,
                        :].loc['Reactor Name'],
                    assem_size=BWR_cond['assem_size'],
                    n_assem_core=BWR_cond['n_assem_core'],
                    n_assem_batch=BWR_cond['n_assem_batch'],
                    capacity=reactor_data.iloc[
                        element,
                        :].loc['Net Electric Capacity'])

                with open(output_name, 'a+') as output:
                    output.write(reactor_body + "\n \n")

            else:
                print(
                    'Warning: specifications of this reactor type have not been given.  Using placeholder values.')

                reactor_body = template.render(
                    reactor_name=reactor_data.iloc[
                        element,
                        :].loc['Reactor Name'],
                    assem_size=PWR_cond['assem_size'],
                    n_assem_core=PWR_cond['n_assem_core'],
                    n_assem_batch=PWR_cond['n_assem_batch'],
                    capacity=reactor_data.iloc[
                        element,
                        :].loc['Net Electric Capacity'])

                with open(output_name, 'a+') as output:
                    output.write(reactor_body + "\n \n")

    # the filename of the rendered reactor is returned to use it as an input
    # later
    return output_name


def write_region(
        reactor_data,
        deployment_data,
        region_template,
        output_name='rendered-region.xml'):
    """

    ***Warning!  This function will check to see if there is already a file 'output_name' in the current directory,
    and if one is found it will be deleted.  Please be aware of this when choosing file names.***

    Function renders the region portion of the Cyclus input file.

    Input:
    reactor_data: the reactor data, as a pandas dataframe.
    deployment data: Dictionary object giving values for initial deployment of each facility type,
                    key names: n_mine, n_enrichment, n_reactor, n_repository
    region_template: name of region template file
    output_name: filenname of rendered region, default: 'rendered-region.xml'

    Output:
    rendered region input filename

    """
    # first, if the file output_name already exists, it is deleted.
    if os.path.exists('./' + output_name) is True:
        os.remove(output_name)

    # then the region template is loaded.
    template = load_template(region_template)

    # the function splits between multiple and single data sets, then renders the region and writes
    # it to the file output_name.  .iloc and .loc are used to obtain specific elements within the
    # reactor_data dataframe.

    # Should this use .size() to include NaN values, or is it better to use
    # .count()?  Why qould you have NaN values?
    reactor_data = reactor_data.drop(['Type'], 'columns')
    reactor_data = reactor_data.groupby(
        reactor_data.columns.tolist()).size().reset_index().rename(
        columns={
            0: 'Number Reactors'})

    country_reactors = {}
    countries_keys = reactor_data.loc[:, 'Country'].drop_duplicates()
    operator_keys = reactor_data.loc[:, 'Operator'].drop_duplicates()

    for country in countries_keys.tolist():

        country_operators = {}
        for operator in operator_keys.tolist():

            reactor_dict = {}
            data_loop = reactor_data.query(
                'Country == @country & Operator == @operator ')

            for element in range(len(data_loop)):
                reactor_dict[
                    data_loop.iloc[
                        element, :].loc['Reactor Name']] = [
                    data_loop.iloc[
                        element, :].loc['Number Reactors'], data_loop.iloc[
                        element, :].loc['Net Electric Capacity']]

            country_operators[operator] = reactor_dict

        country_reactors[country] = country_operators

    region_body = template.render(country_reactor_dict=country_reactors,
                                  countries_infra=deployment_data)

    with open(output_name, 'a+') as output:
        output.write(region_body)

    # the filename of the rendered region file is returned to be used as an
    # input later
    return output_name


def write_recipes(
        fresh,
        spent,
        recipe_template,
        output_name='rendered-recipe.xml'):
    """

    ***Warning!  This function will check to see if there is already a file 'output_name' in the current directory,
    and if one is found it will be deleted.  Please be aware of this when choosing file names.***

    Function renders the recipe portion of the Cyclus input file.

    Input:
    fresh: dictionary object, in id:comp format, containing the isotope names
                and compositions (in mass basis) for fresh fuel
    spent: as fresh_comp, but for spent fuel
    recipe_template: name of recipe template file
    output_name: desired name of output file, default: 'rendered-recipe.xml'

    Output:
    rendered recipe input file

    """

    # if a file named output_name already exists, it's deleted.
    if os.path.exists('./' + output_name) is True:
        os.remove(output_name)

    # load_template is used to load the recipe template
    template = load_template(recipe_template)

    # There is a loop within the recipe template, that creates a new <nuclide></nuclide> subsection
    # for each element in the fresh and spent fuel dictionaries, which is why
    # a loop does not need to be used here.
    recipe_body = template.render(
        fresh_fuel=fresh,
        spent_fuel=spent)

    with open(output_name, 'w') as output:
        output.write(recipe_body)

    # the output filename is returned, to be used later.
    return output_name


def write_main_input(
        simulation_parameters,
        reactor_file,
        region_file,
        recipe_file,
        input_template,
        output_name='rendered-main-input.xml'):
    """

    ***Warning!  This function will check to see if there is already a file 'output_name' in the current directory,
    and if one is found it will be deleted.  Please be aware of this when choosing file names.***

    Function renders the final, main input file for a Cyclus simulation.

    Input:
    simulation_parameters: specifcs of cyclus simulation, containing the data: [duration, start month, start year]
    reactor_file: rendered reactor portion
    region_file: rendered region file
    recipe_file: rendered recipe file
    main_input_template: name of main input template file
    output_name: desired name of output file, default: 'rendered-main-input.xml'

    Output:
    rendered Cyclus input file

    """

    # if a file named output_name already exists, it is deleted.
    if os.path.exists('./' + output_name) is True:
        os.remove(output_name)

    # the main input template is loaded using load_template
    template = load_template(input_template)

    # the next three steps read the rendered reactor, region, and recipe portions, that were
    # made using write_reactor, write_region, and write_recipes, into the notebook.  By assigning them to variables,
    # they can be called when the body of the template is rendered.
    with open(reactor_file, 'r') as reactorf:
        reactor = reactorf.read()

    with open(region_file, 'r') as regionf:
        region = regionf.read()

    with open(recipe_file, 'r') as recipef:
        recipe = recipef.read()

    # because the reactor, region, and recipe portions were already rendered, the function
    # does not need to check for how many reactors were loaded, index using .iloc and .loc, or directly
    # use any of the data aside from the input that describes when the simulation starts and its
    # duration.  Note that reactor, region, and recipe all contain the entire .xml file that was rendered.
    # In the main input template, the variables reactor_input, region_input, and recipe_input are only
    # contained within the root <simulation></simulation> brackets.  It may be helpful to compare the
    # blank template used for reactor, region, or recipe to the main input template to see the proper
    # syntax for inserting a pre-rendered xml file into another.
    main_input = template.render(
        duration=simulation_parameters[0],
        start_month=simulation_parameters[1],
        start_year=simulation_parameters[2],
        decay=simulation_parameters[3],
        reactor_input=reactor,
        region_input=region,
        recipe_input=recipe)

    with open(output_name, 'w') as output:
        output.write(main_input)

    # nothing is returned, but the file output_name should appear once this
    # function completes.


def import_csv(csv_file):
    """
    Function imports the contents of a csv file as a dataframe.

    Input:
    csv_file: name of the csv file of interest.

    Output:
    reactor_data: the data contained in the csv file as a dataframe

    note:  this function requires pandas imported as pd

    """

    # This function takes the contents of the csv file and reads them into a dataframe.
    # one important thing to note is that the functions used later, specifically write_reactor
    # and write_region, expect that the header name for country, reactor name, reactor type,
    # net electric capacity, and operator are 'Country', 'Reactor Name', 'Type',
    # 'Net Electric Capacity', and 'Operator, respectively.  These headers are used
    # to find values within the dataframe.

    reactor_data = (
        pd.read_csv(
            csv_file,
            names=[
                'Country',
                'Reactor Name',
                'Type',
                'Net Electric Capacity',
                'Operator'],
            skiprows=[0]))

    return reactor_data

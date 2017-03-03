#!/usr/bin/env python2.6
# -*- coding: utf-8

import base64
import getpass
import optparse
import random
import threading
import time
from Queue import Queue

from ds_helper import COLORS, print_for_ds, extract, is_contains

import sys
sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/ecdsa-0.13-py2.6.egg/')
sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/requests-2.9.1-py2.6.egg')
#sys.path.insert(1, '/home/erkki/.local/lib/python2.6/site-packages/paramiko-1.16.0-py2.6.egg')
sys.path.insert(1, '/home/butko/.local/lib/python2.6/site-packages/netmiko-1.1.0-py2.6.egg')


from netmiko import ConnectHandler, NetMikoTimeoutException, NetMikoAuthenticationException


log_file_format = "%y%m%d_%H%M%S_{ds_name}.log"


COMPLETE, FATAL, TEMPORARY = 'complete', 'fatal', 'temporary'
NAME, RESULT, PRINTOUTS = 'name', 'result', 'printouts'


RETRY_CONNECTION_LIMIT = 5
FAIL_CONNECTION_WAIT_INTERVALS = [2, 3, 3, 7, 9, 13, 17, 25, 39]
RANDOM_WAIT_TIME = 5

ds_name_pattern = r"\b\w+?\d-\w+?\d{0,4}\b"
comment_line_pattern = r"^\s*?[#/][^\n]+$"


def post_result(result, queue=None, log_file_name=None):
    """

    :param result: {NAME: name, RESULT: result}
    :type result: dict 
    :param queue: Queue object, where result posted
    :type queue: Queue
    :param log_file_name: 
    :type log_file_name: str
    :rtype: None
    """
    if queue:
        queue.put(result)
    if log_file_name:
        try:
            with open(log_file_name, 'a') as log_file:
                log_file.write("[{0}] : ***** result: {1} *****\n"
                               .format(result[NAME],
                                       result[RESULT].upper()))
                log_file.close()
        except IOError:
            pass


def execute_commands(ds_name,
                     user,
                     password,
                     commands,
                     result_queue,
                     io_lock=None,
                     log_to_file=False,
                     color=None):
    """
    
    Upgrade ds to new SW
     
    :param ds_name:
    :type ds_name: str
    :param user:
    :type user: str
    :param password:
    :type password: str
    :param commands: list with commands
    :type commands: list
    :param result_queue:
    :type result_queue: Queue
    :param io_lock: 
    :type io_lock: Lock()
    :param log_to_file: 
    :type log_to_file: str
    :param color: 
    :type color: COLORS
    :rtype: None
    """

    if io_lock: time.sleep(RANDOM_WAIT_TIME * random.random())
    if log_to_file:
        log_file_name = time.strftime(log_file_format.format(ds_name=ds_name))
    else:
        log_file_name = None

    # Create object
    paramiters = {
        'device_type': 'alcatel_sros',
        'host': ds_name,
        'port': 22,
        'username': user,
        'password': password,
        'global_delay_factor': 1,
        'ssh_strict': False,
        'timeout': 8.0,
    }

    # Connect and get basic inform
    print_for_ds(ds_name,
                 '=' * 8 + ' Start process ...' + '=' * 8,
                 io_lock,
                 log_file_name,
                 color)

    for tray in range(RETRY_CONNECTION_LIMIT):
        try:
            connection = ConnectHandler(**paramiters)
            break
        except NetMikoTimeoutException as e:
            print_for_ds(ds_name, str(e))
        except NetMikoAuthenticationException as e:
            print_for_ds(ds_name, str(e))
        except Exception as e:
            if tray != RETRY_CONNECTION_LIMIT - 1:
                print_for_ds(ds_name, 'Cannot connect! Try reconnect...', io_lock, log_file_name, color, COLORS.info)
                print_for_ds(ds_name, str(e), io_lock, log_file_name, color, COLORS.info)
            else:
                print_for_ds(ds_name, 'Cannot connect!', io_lock, log_file_name, color, COLORS.error)
                post_result({NAME: ds_name, RESULT: TEMPORARY}, result_queue, log_file_name)
                return
        time.sleep(FAIL_CONNECTION_WAIT_INTERVALS[tray])

    commands_printout = ""
    for command in commands:
        try:
            # print_for_ds(ds_name, command, io_lock, None, color)
            commands_printout += connection.send_command(command)
            # print_for_ds(ds_name, commands_printout, io_lock, None, color)
        except IOError:
            print_for_ds(ds_name, "Error while execute command {0}".format(command))

    print_for_ds(ds_name,
                 '=' * 8 + ' Finish process.' + '=' * 8,
                 io_lock,
                 log_file_name,
                 COLORS.ok)
    post_result({NAME: ds_name, RESULT: COMPLETE, PRINTOUTS: commands_printout}, result_queue, log_file_name)


if __name__ == "__main__":
    parser = optparse.OptionParser(description='Command execute.',
                                   usage="usage: %prog [-f <DS list file> | ds ds ds ...] -c command")
    parser.add_option("-f", "--file", dest="ds_list_file_name",
                      help="file with DS list, line started with # or / will be dropped", metavar="FILE")
    parser.add_option("-y", "--yes", dest="force_delete",
                      help="force remove unused SW images (both/boot)",
                      action="store_true", default=False)
    parser.add_option("-n", "--no-thread", dest="no_threads",
                      help="execute nodes one by one sequentially",
                      action="store_true", default=False)
    parser.add_option("-l", "--log-to-file", dest="log_to_file",
                      help="enable logging to file {0}".format(log_file_format),
                      action="store_true", default=False)
    parser.add_option("--no-color", dest="colorize",
                      help="Disable colors",
                      action="store_false", default=True)
    parser.add_option("--pw", "--password", dest="secret",
                      help="encoded password",
                      type="string", default="")
    parser.add_option("-c", "--commands", dest="commands_str",
                      help="string with commands, use ; as separator",
                      type="string")
    parser.add_option("--cf", "--command-file", dest="command_file",
                      help="")

    (options, args) = parser.parse_args()
    ds_list_raw = list(extract(ds_name_pattern, ds) for ds in args if extract(ds_name_pattern, ds))

    if options.ds_list_file_name:
        try:
            with open(options.ds_list_file_name) as ds_list_file:
                for line in ds_list_file.readlines(): ds_list_raw.append(line)
        except IOError as e:
            print COLORS.error+"Error while open file: {file}".format(file=options.ds_list_file_name)+COLORS.end
            print COLORS.error+str(e)+COLORS.end

    ds_list = list()
    for ds_str in ds_list_raw:
        ds = extract(ds_name_pattern, ds_str)
        if not is_contains(comment_line_pattern, ds_str) and ds and ds not in ds_list:
            ds_list.append(ds)

    if not ds_list or len(ds_list) < 1:
        print(COLORS.error+"No ds found in arguments."+COLORS.end)
        parser.print_help()
        exit()

    commands_raw = list()
    if options.commands_str:
        for command in options.commands_str.split(";"):
            commands_raw.append(command)
    if options.command_file:
        try:
            with open(options.command_file, "r") as command_file:
                for command_line in command_file.readlines():
                    commands_raw.append(command_file)
        except IOError as e:
            print(COLORS.error+"Error while open file: {file}".format(file=options.command_file)+COLORS.end)
            print(str(e))

    commands = list()
    for command_raw in commands_raw:
        if not is_contains(comment_line_pattern, command_raw):
            commands.append(command_raw)

    if not commands or len(commands) < 1:
        print(COLORS.error+"Cnn't find command."+COLORS.end)
        parser.print_help()
        exit()

    user = getpass.getuser()
    if options.secret:
        secret = base64.b64decode(options.secret).encode("ascii")
    else:
        secret = getpass.getpass('Password for DS:')

    print COLORS.info+"Start running: {0}".format(time.strftime("%H:%M:%S"))+COLORS.end
    start_time = time.time()

    io_lock = threading.Lock()
    result = {COMPLETE: list(), FATAL: list(), TEMPORARY: ds_list, PRINTOUTS: {}}
    colorIndex = 0
    ds_colors = {}

    while result[TEMPORARY]:
        result_queue, threads = Queue(), list()

        if options.no_threads or len(ds_list) == 1:
            handled_ds_count = 0
            start_tour_time = time.time()

            for ds_name in result[TEMPORARY]:
                if ds_name not in ds_colors:
                    ds_colors[ds_name] = None
                try:
                    execute_commands(ds_name,
                                     user,
                                     secret,
                                     commands,
                                     result_queue,
                                     log_to_file=options.log_to_file,
                                     color=ds_colors[ds_name])
                except Exception as e:
                    print_for_ds(ds_name, "**! Unhandled exception " + str(e), ds_colors[ds_name], COLORS.error)
                    result_queue.put({RESULT: FATAL, NAME: ds_name})
                current_time = time.time()
                handled_ds_count += 1
                print '\n' + COLORS.info +\
                      '=' * 8 + \
                      ' total: {0}\t complete: {1}\t remaining: {2} '.format(len(result[TEMPORARY]),
                                                                             handled_ds_count,
                                                                             len(result[TEMPORARY])-handled_ds_count) + \
                      '=' * 8
                print '=' * 4 + \
                      ' time elapsed: {0}\t time remaining: {1} '.format(time.strftime('%H:%M:%S',
                                                                                       time.gmtime(current_time - start_time)),
                                                                         time.strftime('%H:%M:%S',
                                                                                       time.gmtime((current_time-start_tour_time)/handled_ds_count*(len(result[TEMPORARY])-handled_ds_count)))) + \
                      '=' * 4 + \
                      '\n' + COLORS.end
        else:
            for ds_name in result[TEMPORARY]:
                if ds_name not in ds_colors:
                    if options.colorize:
                        ds_colors[ds_name] = COLORS.colors[colorIndex]
                        colorIndex = (colorIndex + 1) % len(COLORS.colors)
                    else:
                        ds_colors[ds_name] = None

                thread = threading.Thread(target=execute_commands, name=ds_name, args=(ds_name,
                                                                                       user,
                                                                                       secret,
                                                                                       commands,
                                                                                       result_queue,
                                                                                       io_lock,
                                                                                       options.log_to_file,
                                                                                       ds_colors[ds_name]))
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

        result[TEMPORARY] = list()

        while not result_queue.empty():
            thread_result = result_queue.get()
            result[thread_result[RESULT]].append(thread_result[NAME])
            if thread_result[RESULT] == COMPLETE:
                result[PRINTOUTS][thread_result[NAME]] = thread_result[PRINTOUTS]

        # determinate ds with unhandled error and mark it as FATAL
        unhandled_ds = list()
        for ds_name in ds_list:
            if ds_name not in result[COMPLETE] and \
                            ds_name not in result[TEMPORARY] and \
                            ds_name not in result[FATAL]:
                unhandled_ds.append(ds_name)

        for ds_name in unhandled_ds:
            result[FATAL].append(ds_name)
            if options.log_to_file:
                post_result({NAME: ds_name, RESULT: FATAL},
                            None,
                            time.strftime(log_file_format.format(ds_name=ds_name)))

        for ds_complete in sorted(result[COMPLETE]):
            if ds_colors[ds_complete]:
                print(ds_colors[ds_complete]+"\t\tResult for {0}".format(ds_complete)+COLORS.end)
                print(ds_colors[ds_complete]+result[PRINTOUTS][ds_complete].format(ds_complete)+COLORS.end)
                print(ds_colors[ds_complete]+"\t\tFinish for {0}".format(ds_complete) + COLORS.end)
            else:
                print("\t\tResult for {0}".format(ds_complete))
                print(result[PRINTOUTS][ds_complete].format(ds_complete))
                print("\t\tFinish for {0}".format(ds_complete))

        if options.colorize and not options.no_threads:
            line_complete, line_temporary, line_fatal = COLORS.end, COLORS.end, COLORS.end
        else:
            line_complete, line_temporary, line_fatal = '', '', ''

        for ds in sorted(result[COMPLETE]):
            if ds_colors[ds]:
                line_complete += ds_colors[ds] + ds + COLORS.end + " "
            else:
                line_complete += ds + " "
        for ds in sorted(result[TEMPORARY]):
            if ds_colors[ds]:
                line_temporary += ds_colors[ds] + ds + COLORS.end + " "
            else:
                line_temporary += ds + " "
        for ds in sorted(result[FATAL]):
            if ds_colors[ds]:
                line_fatal += ds_colors[ds] + ds + COLORS.end + " "
            else:
                line_fatal += ds + " "

        if result[COMPLETE]:  print    COLORS.ok + "\nComplete on       : " + line_complete + COLORS.end
        if result[TEMPORARY]: print COLORS.warning + "Temporary fault on: " + line_temporary + COLORS.end
        if result[FATAL]:     print   COLORS.fatal + "Fatal error on    : " + line_fatal + COLORS.end

        if not result[TEMPORARY]: break  # finish try loading
        answer = ''
        while answer not in ["Y", "N"]:
            answer = raw_input("\nRepeat load on temporary faulty nodes (Y-yes): ").strip().upper()
        if answer != "Y": break
        print

    print COLORS.info + "\nFinish running: {0}".format(time.strftime("%H:%M:%S"))
    print 'Time elapsed: {0}'.format(time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))) + COLORS.end

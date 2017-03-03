#!/usr/bin/env python2.6
# -*- coding: utf-8
import base64
import getpass
import optparse
import random
import threading
import time

from Queue import Queue

from ds_helper import COLORS, print_for_ds, print_message_format, extract, is_contains

log_file_format = "%y%m%d_%H%M%S_{ds_name}.log"


COMPLETE, FATAL, TEMPORARY = 'complete', 'fatal', 'temporary'
NAME, RESULT = 'name', 'result'


RETRY_CONNECTION_LIMIT = 5
FAIL_CONNECTION_WAIT_INTERVALS = [2, 3, 3, 7, 9, 13, 17, 25, 39]
RANDOM_WAIT_TIME = 5


def update_ds(ds_name,
              user,
              password,
              result_queue=Queue(),
              io_lock=None,
              force_delete=False,
              log_to_file=False,
              color=None,
              force_load=False):
    """
    
    Upgrade ds to new SW
     
    :param ds_name:
    :type ds_name: str
    :param user:
    :type user: str
    :param password:
    :type password: str
    :param result_queue:
    :type result_queue: Queue
    :param io_lock: 
    :type io_lock: Lock()
    :param force_delete: 
    :type force_delete: bool
    :param log_to_file: 
    :type log_to_file: str
    :param color: 
    :type color: COLORS
    :param force_load: 
    :type force_load: bool
    :rtype: None
    """

    if io_lock: time.sleep(RANDOM_WAIT_TIME * random.random())
    if log_to_file:
        log_file_name = time.strftime(log_file_format.format(ds_name=ds_name))
    else:
        log_file_name = None

    # Create object
    node = DS(ds_name, user, password)

    # Connect and get basic inform
    print_for_ds(ds_name,
                 '=' * 8 + ' Start process for {ds} '.format(ds=node.ip) + '=' * 8,
                 io_lock,
                 log_file_name,
                 color)

    for tray in range(RETRY_CONNECTION_LIMIT):
        try:
            node.conn()
            break
        except ExceptionWrongPassword:
            print_for_ds(ds_name, 'Wrong password', io_lock, log_file_name, color, COLORS.error)
            post_result({NAME: ds_name, RESULT: FATAL}, result_queue, log_file_name)
            return
        except ExceptionHostUnreachable:
            print_for_ds(ds_name, 'Cannot connect!', io_lock, log_file_name, color, COLORS.error)
            post_result({NAME: ds_name, RESULT: FATAL}, result_queue, log_file_name)
            return
        except :
            if tray != RETRY_CONNECTION_LIMIT - 1:
                print_for_ds(ds_name, 'Cannot connect! Try reconnect...', io_lock, log_file_name, color)
            else:
                print_for_ds(ds_name, 'Cannot connect!', io_lock, log_file_name, color, COLORS.error)
                post_result({NAME: ds_name, RESULT: TEMPORARY}, result_queue, log_file_name)
                return
        time.sleep(FAIL_CONNECTION_WAIT_INTERVALS[tray])


    print_for_ds(ds_name,
                 '=' * 8 + ' Finish process for {ds} '.format(ds=node.ip) + '=' * 8,
                 io_lock,
                 log_file_name,
                 COLORS.ok)
    post_result({NAME: ds_name, RESULT: COMPLETE}, result_queue, log_file_name)


if __name__ == "__main__":
    parser = optparse.OptionParser(description='Prepare DS upgrade SW to \"{0}\" version.'.format(target_sw_version),
                                   usage="usage: %prog [-y] [-n] [-l] [-f <DS list file> | ds ds ds ...]")
    parser.add_option("-f", "--file", dest="ds_list_file_name",
                      help="file with DS list, line started with # or / will be dropped", metavar="FILE")
    parser.add_option("-y", "--yes", dest="force_delete",
                      help="force remove unused SW images (both/boot)",
                      action="store_true", default=False)
    parser.add_option("-n", "--no-thread", dest="no_threads",
                      help="execute nodes one by one sequentially",
                      action="store_true", default=False)
    parser.add_option("-l", "--log-to-file", dest="log_to_file",
                      help="enable logging to file yymmdd_hhmmss_ds-name.log",
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

    if not ds_list:
        parser.print_help()
        exit()

    if len(ds_list) < 1:
        print COLORS.error+"No ds found in arguments."+COLORS.end
        exit()

    user = getpass.getuser()
    if options.secret:
        secret = base64.b64decode(options.secret).encode("ascii")
    else:
        secret = getpass.getpass('Password for DS:')

    print COLORS.info+"Start running: {0}".format(time.strftime("%H:%M:%S"))+COLORS.end
    start_time = time.time()

    if len(ds_list) == 1:
        update_ds(ds_list[0],
                  user,
                  secret,
                  force_delete=options.force_delete,
                  log_to_file=options.log_to_file)
    else:
        io_lock = threading.Lock()
        result = {COMPLETE: list(), FATAL: list(), TEMPORARY: ds_list}
        colorIndex = 0
        ds_colors = {}

        while result[TEMPORARY]:

            result_queue, threads = Queue(), list()

            if options.no_threads:
                handled_ds_count = 0
                start_tour_time = time.time()

                for ds_name in result[TEMPORARY]:
                    if ds_name not in ds_colors:
                        ds_colors[ds_name] = None
                    try:
                        update_ds(ds_name,
                                  user,
                                  secret,
                                  result_queue=result_queue,
                                  force_delete=options.force_delete,
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

                    thread = threading.Thread(target=update_ds, name=ds_name, args=(ds_name,
                                                                                    user,
                                                                                    secret,
                                                                                    result_queue,
                                                                                    io_lock,
                                                                                    options.force_delete,
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

            if options.colorize and not options.no_threads:
                line_complete, line_temporary, line_fatal = COLORS.end, COLORS.end, COLORS.end
            else:
                line_complete, line_temporary, line_fatal = '', '', ''

            for ds in sorted(result[COMPLETE]):
                if options.colorize and not options.no_threads:
                    line_complete += ds_colors[ds] + ds + COLORS.end + " "
                else:
                    line_complete += ds + " "
            for ds in sorted(result[TEMPORARY]):
                if options.colorize and not options.no_threads:
                    line_temporary += ds_colors[ds] + ds + COLORS.end + " "
                else:
                    line_temporary += ds + " "
            for ds in sorted(result[FATAL]):
                if options.colorize and not options.no_threads:
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

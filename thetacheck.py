import argparse
import subprocess
import os
import glob
import traceback
import time
import random
import re

try:
    import tqdm
except ImportError:
    tqdm_enabled = False
else:
    tqdm_enabled = True
try:
    try:
        from gamma import call_with_io
    except ImportError:
        from _gamma import call_with_io
except ImportError:
    def call_with_io(command, string=""):
        bytes_input = string.encode("utf-8")
        process = subprocess.run(command, shell=True, input=bytes_input, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        result = process.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")
        return result

def call_for_status_code(command, string=""):
    bytes_input = string.encode("utf-8")
    try:
        out = subprocess.check_output(command, shell=True, input=bytes_input)
    except subprocess.CalledProcessError as e:
        return e.returncode
    else:
        return 0

def call_with_io_timed(command, string=""):
    start = time.time()
    result = call_with_io(command, string)
    end = time.time()
    return result, end - start

def readfile(filename):
    with open(filename, "r") as file:
        result = file.read()
    return result

def main(app, directory, checker=None, verbose=False, extra_verbose=False, result_dist=None,
                         one_file=None, limit=None, shuffle=False, do_sort=False, natural_sort=False,
                         empty_means_any=True, timer=False):
    def verbose_print(*args, **kwargs):
        if verbose: return print(*args, **kwargs)
    def extra_verbose_print(*args, **kwargs):
        if extra_verbose: return print(*args, **kwargs)
    verbose = verbose or extra_verbose
    if one_file is not None:
        all_files = [f for f in [one_file + ".in", one_file + ".out"] if os.path.exists(f)]
        files = [one_file + ".in"]
        approx_total = 1
    else:
        all_files = {os.path.join(directory, f) for f in os.listdir(directory)}
        files = glob.glob(os.path.join(directory, "*.in"))
        approx_total = len(glob.glob(os.path.join(directory, "*.in")))
    if shuffle:
        random.shuffle(files)
    elif do_sort:
        files.sort(key=lambda f: os.path.getsize(f))
    elif natural_sort:
        def tryint(f):
            try: return int(f)
            except: return f
        files.sort(key=lambda f: [tryint(c) for c in re.split("([0-9]+)", f)])
    if limit is not None and approx_total > limit:
        files = files[:limit]
        approx_total = limit
    total = 0
    correct = 0
    overtime_count = 0
    wrong = []
    overtime = []
    times = []
    try:
        if tqdm_enabled and not verbose:
            it = tqdm.tqdm(files)
            tqdm_running = True
        else:
            it = files
            tqdm_running = False
        for file in it:
            test_name = file[:-3]
            infile, outfile = file, test_name + ".out"
            filenote = " ({} & {})".format(infile, outfile) if extra_verbose else ""
            verbose_print("Test {}{}, done {} out of {} ({}%)".format(test_name, filenote, total, approx_total,
                                                                      round(total / approx_total * 100, 2)))
            indata = readfile(infile).strip()
            if outfile not in all_files:
                if not empty_means_any and checker is None:
                    if tqdm_running: print()
                    print("[Error] Missing out file for test {}".format(infile))
                    approx_total -= 1
                    continue
                else:
                    outdata = ""
            else:
                outdata = readfile(outfile).strip()
            if not indata:
                if tqdm_running: print()
                print("[Error] The input file for test {} is empty".format(infile))
                approx_total -= 1
                continue
            extra_verbose_print("Input:\n{}".format(indata))
            extra_verbose_print("Expected output:\n{}".format(outdata if outdata else "[[None given]]"))
            try:
                out, time_taken = call_with_io_timed(app, indata)
                out = out.strip()
            except Exception:
                if tqdm_running: print()
                print("[Error] Got exception while executing test {} with {}".format(test_name, app))
                traceback.print_exc()
            else:
                if verbose and (timer or time_taken > 1):
                    print("Process took {} seconds".format(round(time_taken, 2)))
                if time_taken > 1:
                    overtime_count += 1
                    overtime.append(test_name)
                if timer:
                    times.append(time_taken)
                extra_verbose_print("Got:\n{}".format(out))
                if result_dist is not None:
                    # Floating point precision, goddammit.
                    is_correct = round(abs(float(outdata) - float(out)), 10) <= result_dist
                elif checker is not None:
                    checker_input = indata + "\n" + out
                    code = call_for_status_code(checker, checker_input)
                    outdata = f"[[Got status code {code} from {checker}]]"
                    extra_verbose_print(f"Checker: {outdata}")
                    is_correct = code == 0
                else:
                    is_correct = (empty_means_any and not outdata) or outdata == out
                if is_correct:
                    verbose_print("[+] Correct")
                    correct += 1
                else:
                    if not extra_verbose:
                        verbose_print("[-] Wrong\nExpected:\n{}\nGot:\n{}".format(outdata, out))
                    wrong.append(test_name)
                total += 1
    except KeyboardInterrupt:
        # Break the testing loop and print the statistics after Ctrl-C is pressed
        pass
    print("Done testing {}".format(app))
    if not total:
        print("No valid tests were found")
        return False
    print("Correct {} out of {} ({}%)".format(correct, total, round(correct / total * 100, 2)))
    if wrong:
        print("Tests that failed:")
        print(*wrong, sep=", ")
    if overtime:
        print("{} out of {} ({}%) tests went overtime:".format(overtime_count, total, round(overtime_count / total * 100, 2)))
        print(*overtime, sep=", ")
    if timer:
        print("Times: {}".format(", ".join(str(round(t, 4)) for t in times if round(t, 4))))
    return True

DESCRIPTION = "thetacheck: given an app (-a or --app) and test directory (-d or --dir) that contains " \
              "text files named <name>.in and <name>.out returns statistics of the correctness of the app. " \
              "Use -h or --help for help."

parser = argparse.ArgumentParser(description=DESCRIPTION)
parser.add_argument("-a", "--app", help="The application used for testing", required=False)
parser.add_argument("-c", "--checker", help="The application used for checking answers - should accept the .in and .out file contents" \
                                             " (as newline-separated strings on the standard input stream)" \
                                             " and return status code 0 if the answers are correct", required=False)

parser.add_argument("-v", "--verbose", action="store_true", help="Print out additional data during testing")
parser.add_argument("-ev", "--extra_verbose", action="store_true", help="Print out even more data during testing")
parser.add_argument("-rd", "--result_dist", type=float, default=None,
                    help="Interpret the result/expected output as *one* number" \
                         " and accept the result if it is within the given distance")
parser.add_argument("-l", "--limit", default=None, type=int, help="Only run a given amount of tests")
parser.add_argument("-x", "--auto", action="store_true", help="Automatically locate the tests directory and app")
parser.add_argument("-e", "--empty_means_any", action="store_true", help="If the .out file is empty or missing the result is always counted as correct")
parser.add_argument("-t", "--timer", action="store_true", help="Print the time taken by the application")

ordering_arggroup = parser.add_mutually_exclusive_group(required=False)
ordering_arggroup.add_argument("-s", "--shuffle", action="store_true", help="Shuffle the tests randomly")
ordering_arggroup.add_argument("-S", "--do_sort", action="store_true", help="Sort the tests by size")
ordering_arggroup.add_argument("-N", "--natural_sort", action="store_true", help="Sort the tests using natural/human sorting")

file_arggroup = parser.add_mutually_exclusive_group(required=False)
file_arggroup.add_argument("-d", "--dir", default=None, help="The directory where the tests are to be found")
file_arggroup.add_argument("-o", "--one_file", default=None, help="Only run the program for one file (test name is given)")


if __name__ == "__main__":
    args = parser.parse_args()
    app, directory, checker, verbose, extra_verbose = args.app, args.dir, args.checker, args.verbose, args.extra_verbose
    result_dist, one_file, limit = args.result_dist, args.one_file, args.limit
    shuffle, do_sort, natural_sort, auto = args.shuffle, args.do_sort, args.natural_sort, args.auto
    empty_means_any, timer = args.empty_means_any, args.timer
    if auto and not (app or directory):
        exelist = glob.glob("*.exe")
        if len(exelist) == 1:
            app = exelist[0]
        else:
            parser.error("Ambiguous --auto switch, found: {} applications".format(len(exelist)))
        directory = "tests"
    if not app and not auto:
        parser.error("app argument not provided, nor the --auto switch was enabled")
    if not directory:
        print("directory argument not provided{}. using cwd (tests/)".format(", nor the --auto switch was enabled" if not auto else ""))
        directory = "tests"
    if not shuffle and not do_sort and not natural_sort:
        natural_sort = True
    # app = os.path.abspath(app)
    directory = os.path.normpath(directory) if directory else os.path.realpath(one_file)
    main(app, directory, checker, verbose, extra_verbose, result_dist, one_file, limit, shuffle, do_sort, natural_sort, empty_means_any, timer)

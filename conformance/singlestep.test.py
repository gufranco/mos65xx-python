import contextlib
import importlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "conformance"))

singlestep = importlib.import_module("singlestep")


def a_test(**changes):
    initial = {
        "pc": 0x8000,
        "s": 0x01FF,
        "p": 0x00,
        "a": 0x1234,
        "x": 0x0056,
        "y": 0x0078,
        "dbr": 0x12,
        "d": 0x0000,
        "pbr": 0x00,
        "e": 0,
        "ram": [[0x008000, 0xEA]],
    }
    final = dict(initial, pc=0x8001, ram=[[0x008000, 0xEA]])
    found = {"name": "ea n 0", "initial": initial, "final": final, "cycles": []}
    found.update(changes)
    return found


class LoadTest(unittest.TestCase):
    def test_a_missing_suite_reports_itself_rather_than_raising(self):
        self.assertEqual(singlestep.suite_files(Path("/nowhere/at/all")), [])

    def test_files_come_back_sorted_so_a_run_is_reproducible(self):
        with tempfile.TemporaryDirectory() as where:
            for name in ("ff.n.json", "00.n.json", "7a.e.json"):
                (Path(where) / name).write_text("[]")

            found = [path.name for path in singlestep.suite_files(where)]

        self.assertEqual(found, ["00.n.json", "7a.e.json", "ff.n.json"])

    def test_anything_that_is_not_a_test_file_is_left_alone(self):
        with tempfile.TemporaryDirectory() as where:
            (Path(where) / "00.n.json").write_text("[]")
            (Path(where) / "README.md").write_text("not a suite")

            found = [path.name for path in singlestep.suite_files(where)]

        self.assertEqual(found, ["00.n.json"])


class StateTest(unittest.TestCase):
    def test_the_initial_state_reaches_every_register(self):
        cpu, _ = singlestep.machine_for(a_test()["initial"])

        self.assertEqual(cpu.a, 0x1234)
        self.assertEqual(cpu.x, 0x0056)
        self.assertEqual(cpu.y, 0x0078)
        self.assertEqual(cpu.db, 0x12)
        self.assertEqual(cpu.pb, 0x00)
        self.assertEqual(cpu.pc, 0x8000)

    def test_the_emulation_flag_is_taken_from_the_test(self):
        cpu, _ = singlestep.machine_for(dict(a_test()["initial"], e=1))

        self.assertTrue(cpu.emulation)

    def test_memory_outside_the_test_is_not_assumed_clear(self):
        _, memory = singlestep.machine_for(a_test()["initial"])

        far = [memory.read8(at) for at in range(0x400000, 0x400040)]

        self.assertNotEqual(far, [0] * 64)

    def test_the_bytes_the_test_names_are_placed(self):
        _, memory = singlestep.machine_for(a_test()["initial"])

        self.assertEqual(memory.read8(0x008000), 0xEA)


class CompareTest(unittest.TestCase):
    def test_a_matching_run_reports_nothing(self):
        self.assertEqual(singlestep.check(a_test()), [])

    def test_a_wrong_register_is_named(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], a=0x9999)

        found = singlestep.check(broken)

        self.assertTrue(any(name == "a" for name, _, _ in found))

    def test_a_wrong_memory_byte_is_named_by_its_address(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], ram=[[0x008000, 0x00]])

        found = singlestep.check(broken)

        self.assertTrue(any(name == "$008000" for name, _, _ in found))

    def test_the_status_byte_is_compared(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], p=0xFF)

        self.assertTrue(
            any(name == "p" for name, _, _ in found) for found in [singlestep.check(broken)]
        )


class RunTest(unittest.TestCase):
    def test_a_run_counts_what_passed_and_what_did_not(self):
        passed, failed, examples = singlestep.run_tests([a_test(), a_test()])

        self.assertEqual((passed, failed), (2, 0))
        self.assertEqual(examples, [])

    def test_a_failing_case_is_kept_as_an_example(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], a=0x9999)

        passed, failed, examples = singlestep.run_tests([broken])

        self.assertEqual((passed, failed), (0, 1))
        self.assertEqual(examples[0][0], "ea n 0")

    def test_only_a_few_examples_are_kept(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], a=0x9999)

        _, _, examples = singlestep.run_tests([broken] * 50)

        self.assertLessEqual(len(examples), singlestep.EXAMPLE_LIMIT)

    def test_a_register_the_test_leaves_out_is_not_compared(self):
        quiet = a_test()
        quiet["final"] = {"pc": 0x8001}

        self.assertEqual(singlestep.check(quiet), [])

    def test_a_run_that_ends_in_the_wrong_mode_is_a_disagreement(self):
        wrong = a_test()
        wrong["final"] = dict(wrong["final"], e=1)

        self.assertIn(("e", 1, 0), singlestep.check(wrong))

    def test_a_case_that_raises_is_counted_rather_than_ending_the_run(self):
        broken = a_test()
        broken["initial"] = dict(broken["initial"], ram="not a list of pairs")

        passed, failed, examples = singlestep.run_tests([broken, a_test()])

        self.assertEqual((passed, failed), (1, 1))
        self.assertEqual(examples[0][1][0][0], "raised")


class FileTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="singlestep-file-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, name, tests):
        path = Path(self.root) / name
        path.write_text(json.dumps(tests))
        return path

    def test_a_file_runs_every_case_it_holds(self):
        path = self.write("ea.n.json", [a_test(), a_test()])

        passed, failed, _ = singlestep.run_file(path)

        self.assertEqual((passed, failed), (2, 0))

    def test_a_limit_takes_only_the_first_few_cases(self):
        path = self.write("ea.n.json", [a_test()] * 10)

        passed, failed, _ = singlestep.run_file(path, limit=3)

        self.assertEqual((passed, failed), (3, 0))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="singlestep-main-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def write(self, name, tests):
        (Path(self.root) / name).write_text(json.dumps(tests))

    def broken_test(self):
        broken = a_test()
        broken["final"] = dict(broken["final"], a=0x9999)
        return broken

    def run_main(self, argv):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = singlestep.main(argv)
        return code, captured.getvalue()

    def test_no_arguments_explains_how_to_call_it(self):
        code, output = self.run_main([])

        self.assertEqual(code, 2)
        self.assertIn("usage", output)

    def test_a_suite_that_is_not_there_says_so_without_failing_the_build(self):
        code, output = self.run_main([str(Path(self.root) / "absent")])

        self.assertEqual(code, 0)
        self.assertIn("no suite at", output)

    def test_a_passing_suite_reports_success(self):
        self.write("ea.n.json", [a_test(), a_test()])

        code, output = self.run_main([str(self.root)])

        self.assertEqual(code, 0)
        self.assertIn("2 agreed, 0 did not", output)

    def test_a_failing_suite_names_the_file_and_the_first_disagreement(self):
        self.write("ea.n.json", [self.broken_test()])

        code, output = self.run_main([str(self.root)])

        self.assertEqual(code, 1)
        self.assertIn("ea.n.json: 1 wrong", output)
        self.assertIn("a want 39321", output)

    def test_a_filter_takes_only_the_files_whose_name_matches(self):
        self.write("ea.n.json", [a_test()])
        self.write("00.n.json", [self.broken_test()])

        code, output = self.run_main([str(self.root), "0", "ea"])

        self.assertEqual(code, 0)
        self.assertIn("1 files", output)

    def test_a_limit_is_taken_from_the_second_argument(self):
        self.write("ea.n.json", [a_test()] * 10)

        _, output = self.run_main([str(self.root), "4"])

        self.assertIn("4 agreed", output)

    def test_only_a_few_broken_files_are_listed_and_the_rest_are_counted(self):
        for index in range(singlestep.EXAMPLE_LIMIT + 2):
            self.write(f"{index:02x}.n.json", [self.broken_test()])

        code, output = self.run_main([str(self.root)])

        self.assertEqual(code, 1)
        self.assertIn("more files with failures", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

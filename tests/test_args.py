#!/usr/bin/env python3
"""
Test that all command-line arguments used in main.py are properly defined.
This helps catch errors where we reference args that don't exist.
"""

import unittest
import re
import sys
import os
import importlib.util
from argparse import Namespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestCommandLineArgs(unittest.TestCase):
    """Test command-line argument handling"""
    
    def setUp(self):
        """Set up the test by loading the main module"""
        # Import the main module
        spec = importlib.util.spec_from_file_location("main", "main.py")
        self.main_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.main_module)
    
    def test_args_match_parser(self):
        """Test that all args referenced in main.py are defined in parse_args()"""
        # Read the main.py file to extract all args references (args.xxx)
        with open("main.py", "r") as f:
            content = f.read()
        
        # Find all occurrences of args.xxx - improved regex to prevent partial matches
        args_refs = set(re.findall(r'args\.([a-zA-Z0-9_]+)(?:\s|[\)\]]|\.|,|$)', content))
        
        # Get the args that are defined in the parser
        parser = self.main_module.parse_args()
        
        # Create a namespace with all the arguments from the parser
        args = vars(parser)
        defined_args = set(args.keys())
        
        # Check that all referenced args are defined
        missing_args = args_refs - defined_args
        
        # Print helpful error message
        if missing_args:
            self.fail(f"The following arguments are referenced in main.py but not defined in parse_args(): {', '.join(missing_args)}")
    
    def test_args_are_used(self):
        """Test that all args defined in the parser are used in main.py"""
        # This is not strictly necessary but helps keep the code clean
        with open("main.py", "r") as f:
            content = f.read()
        
        # Find all occurrences of args.xxx - improved regex to prevent partial matches
        args_refs = set(re.findall(r'args\.([a-zA-Z0-9_]+)(?:\s|[\)\]]|\.|,|$)', content))
        
        # Get the args that are defined in the parser
        parser = self.main_module.parse_args()
        
        # Create a namespace with all the arguments from the parser
        args = vars(parser)
        defined_args = set(args.keys())
        
        # Check that all defined args are referenced
        unused_args = defined_args - args_refs
        
        # Print helpful warning (not a failure)
        if unused_args:
            print(f"Warning: The following arguments are defined in parse_args() but not referenced in main.py: {', '.join(unused_args)}")
            print("This is just a warning, not a test failure.")

if __name__ == '__main__':
    unittest.main() 
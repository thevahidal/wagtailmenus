#!/usr/bin/env python
import argparse
import os
import sys
import warnings

from django.core.management import execute_from_command_line

os.environ['DJANGO_SETTINGS_MODULE'] = 'wagtailmenus.settings.testing'


def make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--deprecation',
        choices=['all', 'pending', 'imminent', 'none'],
        default='imminent'
    )
    return parser


def parse_args(args=None):
    return make_parser().parse_args(args)


def runtests():
    args = parse_args()

    only_wagtailmenus = r'^wagtailmenus(\.|$)'
    if args.deprecation == 'all':
        # Show all deprecation warnings from all packages
        warnings.simplefilter('default', DeprecationWarning)
        warnings.simplefilter('default', PendingDeprecationWarning)
    elif args.deprecation == 'pending':
        # Show all deprecation warnings from wagtail
        warnings.filterwarnings(
            'default', category=DeprecationWarning, module=only_wagtailmenus)
        warnings.filterwarnings(
            'default', category=PendingDeprecationWarning, module=only_wagtailmenus)
    elif args.deprecation == 'imminent':
        # Show only imminent deprecation warnings from wagtail
        warnings.filterwarnings(
            'default', category=DeprecationWarning, module=only_wagtailmenus)
    elif args.deprecation == 'none':
        # Deprecation warnings are ignored by default
        pass

    argv = [sys.argv[0], 'test']
    try:
        execute_from_command_line(argv)
    except:
        pass

if __name__ == '__main__':
    runtests()

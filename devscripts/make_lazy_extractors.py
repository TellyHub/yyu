#!/usr/bin/env python3
from __future__ import unicode_literals, print_function

from inspect import getsource
import io
import os
import re
from os.path import dirname as dirn
import sys

sys.path.insert(0, dirn(dirn((os.path.abspath(__file__)))))

lazy_extractors_filename = sys.argv[1] if len(sys.argv) > 1 else 'yt_dlp/extractor/lazy_extractors.py'
if os.path.exists(lazy_extractors_filename):
    os.remove(lazy_extractors_filename)

# Block plugins from loading
plugins_dirname = 'ytdlp_plugins'
plugins_blocked_dirname = 'ytdlp_plugins_blocked'
if os.path.exists(plugins_dirname):
    os.rename(plugins_dirname, plugins_blocked_dirname)

from yt_dlp.extractor import _ALL_CLASSES
from yt_dlp.extractor.common import InfoExtractor, SearchInfoExtractor, SelfHostedInfoExtractor

if os.path.exists(plugins_blocked_dirname):
    os.rename(plugins_blocked_dirname, plugins_dirname)

with open('devscripts/lazy_load_template.py', 'rt') as f:
    module_template = f.read()

CLASS_PROPERTIES = ['ie_key', 'working', '_match_valid_url', 'suitable', '_match_id', 'get_temp_id']
SH_CLASS_PROPERTIES = ['suitable', '_test_selfhosted_instance', '_is_probe_enabled', '_probe_selfhosted_service', '_probe_webpage', '_fetch_nodeinfo_software']
SH_FIELDS = ('_IMPOSSIBLE_HOSTNAMES', '_PREFIX_GROUPS', '_HOSTNAME_GROUPS', '_INSTANCE_LIST', '_DYNAMIC_INSTANCE_LIST', '_NODEINFO_SOFTWARE', '_SOFTWARE_NAME')
module_contents = [
    module_template,
    *[getsource(getattr(InfoExtractor, k)) for k in CLASS_PROPERTIES],
    '\nclass LazyLoadSearchExtractor(LazyLoadExtractor):\n    pass\n',
    '\nclass LazyLoadSelfHostedExtractor(LazyLoadExtractor):',
    '    _SELF_HOSTED = True\n',
    *[getsource(getattr(SelfHostedInfoExtractor, k)) for k in SH_CLASS_PROPERTIES]]

for fld in SH_FIELDS:
    value = getattr(SelfHostedInfoExtractor, fld, None)
    if value is None:
        continue
    module_contents.append(f'    {fld} = {value!r}')

module_contents.append('')

ie_template = '''
class {name}({bases}):
    _module = '{module}'
'''


def get_base_name(base):
    if base is InfoExtractor:
        return 'LazyLoadExtractor'
    elif base is SearchInfoExtractor:
        return 'LazyLoadSearchExtractor'
    elif base is SelfHostedInfoExtractor:
        return 'LazyLoadSelfHostedExtractor'
    else:
        return base.__name__


def build_lazy_ie(ie, name):
    s = ie_template.format(
        name=name,
        bases=', '.join(map(get_base_name, ie.__bases__)),
        module=ie.__module__)
    valid_url = getattr(ie, '_VALID_URL', None)
    if not valid_url and hasattr(ie, '_make_valid_url'):
        valid_url = ie._make_valid_url()
    if valid_url:
        s += f'    _VALID_URL = {valid_url!r}\n'
    if not ie._WORKING:
        s += '    _WORKING = False\n'
    if ie.suitable.__func__ is not InfoExtractor.suitable.__func__:
        s += f'\n{getsource(ie.suitable)}'
    if getattr(ie, '_SELF_HOSTED', False):
        for fld in SH_FIELDS:
            value = ie.__dict__.get(fld)
            if value is None:
                continue
            s += f'    {fld} = {value!r}\n'

    return s


# find the correct sorting and add the required base classes so that subclasses
# can be correctly created
classes = _ALL_CLASSES[:-1]
ordered_cls = []
while classes:
    for c in classes[:]:
        bases = set(c.__bases__) - set((object, InfoExtractor, SearchInfoExtractor, SelfHostedInfoExtractor))
        stop = False
        for b in bases:
            if b not in classes and b not in ordered_cls:
                if b.__name__ == 'GenericIE':
                    exit()
                classes.insert(0, b)
                stop = True
        if stop:
            break
        if all(b in ordered_cls for b in bases):
            ordered_cls.append(c)
            classes.remove(c)
            break
ordered_cls.append(_ALL_CLASSES[-1])

names = []
for ie in ordered_cls:
    name = ie.__name__
    src = build_lazy_ie(ie, name)
    module_contents.append(src)
    if ie in _ALL_CLASSES:
        names.append(name)

module_contents.append(
    '\n_ALL_CLASSES = [{0}]'.format(', '.join(names)))

module_src = '\n'.join(module_contents) + '\n'
module_src = module_src.replace('SelfHostedInfoExtractor.', 'LazyLoadSelfHostedExtractor.')
module_src = re.sub(r": '[^']+'", '', module_src)

with io.open(lazy_extractors_filename, 'wt', encoding='utf-8') as f:
    f.write(module_src)

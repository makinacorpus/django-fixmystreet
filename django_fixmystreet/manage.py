#!/usr/bin/env python
import pkg_resources
import os
import sys
w=os.path.dirname(__file__)
os.chdir(w)
os.environ['DJANGO_SETTINGS_MODULE'] = os.environ.get('DJANGO_SETTINGS_MODULE', 'django_fixmystreet.settings')

dist = [a for a in pkg_resources.working_set.require('Django') if a.project_name == 'Django'][0]
items = {}

provider = dist._provider
if dist.has_metadata('scripts'):
    for s in provider.metadata_listdir('scripts'):
        if not(s.endswith('.pyc') or s.endswith('.pyo')):
            items[s] = provider._fn(provider.egg_info, 'scripts/%s' % s) 
    
runner = items['django-admin.py']
def main():
    sys.argv.pop(0)
    os.environ['PYTHONPATH'] = ':'.join(sys.path)
    os.execvpe(sys.executable, [sys.executable, runner]+sys.argv, os.environ)
  
if __name__ == "__main__":
    main()


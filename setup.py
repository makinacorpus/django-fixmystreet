from setuptools import setup, find_packages

version = "0.9 beta"

setup(
    name = "django_fixmystreet",
    version = version,
    url = 'https://github.com/makinacorpus/django-fixmystreet',
    license = 'BSD',
    description = "",
    author = 'CIRB',
    packages=find_packages(exclude=['ez_setup']),
    #package_dir = {'': 'src'},
    install_requires = ['setuptools',
                        'ordereddict',
                        'south',
                        'demjson',
                        'django-social-auth',
                        'django-registration',
                        'django'],
    #extras_require = { 'test': ['django-debug-toolbar', 'django-jenkins'] }
    entry_points={
        'console_scripts': [
               'fixmystreet_manage = django_fixmystreet.manage:main',
        ],
    }
)

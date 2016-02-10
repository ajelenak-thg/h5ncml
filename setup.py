from setuptools import setup


VERSION = '0.1.0'

# with open("README.rst", "rb") as f:
#     long_descr = f.read().decode("utf-8")

setup(
    name='h5ncml',
    packages=['h5ncml'],
    entry_points={
        'console_scripts': ['h5ncml = h5ncml.h5ncml:main']},
    version=VERSION,
    description=('Python command line application and module for generating '
                 'NcML from HDF5 files.'),
    # long_description=long_descr,
    author='Aleksandar Jelenak',
    author_email='info@hdfgroup.org',
    install_requires=['numpy>=1.6.1', 'h5py>=2.5.0', 'lxml>=3.5.0']
)

from setuptools import setup, find_packages

setup(name='pylexbuilder',
      version='0.1.0',
      packages=find_packages(),
      description='Python AWS Lex Builder',
      author='WavyCloud',
      author_email='',
      url='https://github.com/wavycloud/pylexbuilder',
      py_modules=['pylexbuilder'],
      install_requires=['schematics==2.0.1'],
      license='MIT License',
      zip_safe=True,
      keywords='aws python lex lambda automation',
      classifiers=[])

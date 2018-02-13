from setuptools import setup, find_packages

setup(name='pylexbuilder',
      version='0.1.0',
      packages=find_packages(),
      description='Python AWS Lex Builder',
      author='WavyCloud',
      author_email='',
      entry_points={
          'console_scripts': [
              'pylexo = pylexo.__main__:main'
          ]
      },
      url='https://github.com/wavycloud/pylexbuilder',
      py_modules=['pylexbuilder'],
      install_requires=['jsonobject==0.7.1'],
      license='MIT License',
      zip_safe=True,
      keywords='aws python lex lambda',
      classifiers=[])

from setuptools import setup, find_packages

setup(
    name='labudy',
    version='0.1.0',
    description='A Python library for research lab buddy',
    author='kenoharada',
    author_email='keno.lasalle.kagoshima@gmail.com',
    license='MIT',
    packages=find_packages('src'),
    package_dir={'': 'src'},      
    install_requires=[
        'openai',
        'google-generativeai',
        'anthropic',
        'tenacity',
        'playwright',
    ],
    python_requires='>=3.8',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/your-username/labudy',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
) 
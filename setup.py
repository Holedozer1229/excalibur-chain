from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="sphinx-os",
    version="1.0.0",
    author="Excalibur-Chain",
    description="SphinxOS Nexus — Grand Unified Quantum Blockchain Organism",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/excalibur-chain/excalibur-chain",
    packages=find_packages(include=["sphinx_os", "sphinx_os.*"]),
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.24.0",
        "cryptography>=41.0.0",
    ],
    extras_require={
        "gui": [
            "customtkinter>=5.2.0",
        ],
        "dev": [
            "pyinstaller>=6.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Security :: Cryptography",
        "Topic :: System :: Distributed Computing",
    ],
    keywords="blockchain quantum consensus p2p treasury",
)

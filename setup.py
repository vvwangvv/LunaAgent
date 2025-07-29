from setuptools import setup, find_packages

# Read requirements.txt
with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="luna_agent",
    version="0.1.0",
    author="Wei Wang",
    description="Luna Agent Service",
    packages=find_packages(),
    install_requires=requirements,
    python_requires=">=3.9",  # adjust as needed
)


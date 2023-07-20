# Pulumi AWS Infrastructure Repo

This repository contains a Pulumi program that deploys a sample AWS infrastructure using ECS, ECR, VPC, and Load Balancer resources. It is developed in Python, using the Pulumi AWS SDK.

Infrastructure Diagram
![system design](images/pulumi_ecs.png)

Key Features
1. This program builds and publishes Docker images using ECR repositories and Dockerfiles for a web UI and a web API.
2. It creates a VPC, public and private subnets, and an internet gateway.
3. It generates two ECS services, one for the web UI and one for the web API, each with their own load balancer and security group.
4. The services run on an ECS cluster with the FARGATE launch type, enabling them to be run without the need to manage servers or clusters.

Prerequisites
Before running this program, ensure you have the following:
"""
Python 3.6 or later
Pulumi CLI
AWS Account and configured AWS credentials
Quick Start
Clone this repository and navigate to the repo's root directory in your terminal.
"""

"""
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
"""

Install the required Python packages:
"""
pip install -r requirements.txt
"""

Set your AWS region e.g:
"""
pulumi config set aws:region us-west-2
"""
Deploy the stack:
"""
pulumi up
"""

The pulumi up command creates and updates resources in your stack. You will be prompted to confirm these actions before they occur.

After the stack has been deployed, Pulumi will print out the URL of the load balancer. Visit the URL to view the web UI.

Clean up your resources:
"""
pulumi destroy
"""
Remember to destroy your resources when you're done to avoid unnecessary AWS charges!

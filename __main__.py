"""A Python Pulumi program"""

import pulumi

from pulumi import Output, export, get_stack
from pulumi_aws import Provider, ecr, ecs, ec2, lb, get_availability_zones, autoscaling, iam, cloudwatch
import pulumi_awsx as awsx
import json
import os

azs_state =  os.environ.get("AZS_STATE", "available")

azs = get_availability_zones(state=azs_state)

# Define shared tags
stack_name = get_stack()
tags = {
    'environment': 'dev',
    'stack_name': stack_name,
}

# Create the ECR Repositories for web-api and web-ui
web_ui_repo = awsx.ecr.Repository('web-ui-repo', tags=tags, force_delete=True)
web_api_repo = awsx.ecr.Repository(
    'web-api-repo', tags=tags, force_delete=True)

# Build and publish the docker image
web_ui_image = awsx.ecr.Image("web-ui-image",
                              repository_url=web_ui_repo.url,
                              dockerfile="../infra-team-test/infra-web/Dockerfile",
                              path="../infra-team-test")

# Build and publish the docker image
web_api_image = awsx.ecr.Image("web-api-image",
                               repository_url=web_api_repo.url,
                               dockerfile="../infra-team-test/infra-api/Dockerfile",
                               path="../infra-team-test")

# Create a new VPC
vpc = ec2.Vpc(stack_name+"-vpc", cidr_block="10.3.0.0/16",
              enable_dns_support=True, tags=tags)

igw = ec2.InternetGateway("igw", vpc_id=vpc.id, tags=tags)

public_route_table = ec2.RouteTable("public-route-table", vpc_id=vpc.id, routes=[
                                    ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", gateway_id=igw.id)], tags=tags)

public_subnet_ids = []
public_subnet_cidr_blocks = []
private_subnet_ids = []
private_subnet_cidr_blocks = []
# Create a public subnet within the VPC
for i, az in enumerate(azs.names, 1):
    if i > 2:  # only create 2 subnets in 2 AZs
        break
    public_cidr_block = f"10.3.1.{i*64}/26"
    public_subnet_cidr_blocks.append(public_cidr_block)
    # public subnet
    public_subnet = ec2.Subnet(f"public-subnet-{i}",
                               cidr_block=public_cidr_block,
                               vpc_id=vpc.id,
                               availability_zone=az,
                               map_public_ip_on_launch=True,
                               tags=tags
                               )
    public_subnet_ids.append(public_subnet.id)
    public_route_table_associaition = ec2.RouteTableAssociation(
        f"public-subnet-association-{i}", route_table_id=public_route_table.id, subnet_id=public_subnet.id)

    eip = ec2.Eip(f'nat-eip-{i}')
    nat_gateway = ec2.NatGateway(f"nat-gateway-{i}",
                                 allocation_id=eip.id,
                                 subnet_id=public_subnet.id,
                                 tags=tags
                                 )

    # private subnet
    private_cidr_block = f"10.3.2.{i*64}/26"
    private_subnet_cidr_blocks.append(private_cidr_block)
    private_subnet = ec2.Subnet(f"private-subnet-{i}",
                                vpc_id=vpc.id,
                                cidr_block=private_cidr_block,
                                availability_zone=az,
                                tags=tags
                                )
    private_subnet_ids.append(private_subnet.id)
    private_route_table = ec2.RouteTable(f"private-route-table-{i}", vpc_id=vpc.id, routes=[
                                         ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", nat_gateway_id=nat_gateway.id)], tags=tags)

    private_route_table_associaition = ec2.RouteTableAssociation(
        f"private-subnet-association-{i}", route_table_id=private_route_table.id, subnet_id=private_subnet.id)


# # Security
# # NACL
# # private
# private_acl = ec2.NetworkAcl("private-acl",
#                              vpc_id=vpc.id,
#                              subnet_ids=private_subnet_ids,
#                              tags=tags)


# private_acl_inbound = ec2.NetworkAclRule(f"private-acl-inbound",
#                                         network_acl_id=private_acl.id,
#                                         rule_number=300,
#                                         egress=False,
#                                         protocol="tcp",
#                                         rule_action="allow",
#                                         cidr_block="0.0.0.0/0",
#                                         from_port=0,
#                                         to_port=65535)

# private_acl_outbound = ec2.NetworkAclRule(f"private-acl-outbound-",
#                                         network_acl_id=private_acl.id,
#                                         rule_number=300,
#                                         egress=True,
#                                         protocol="-1",
#                                         rule_action="allow",
#                                         cidr_block="0.0.0.0/0",
#                                         from_port=0,
#                                         to_port=0)
    
# for i, cidr in enumerate (private_subnet_cidr_blocks):
#     private_acl_inbound = ec2.NetworkAclRule(f"private-acl-inbound-{i+1}",
#                                             network_acl_id=private_acl.id,
#                                             rule_number=200 + i*10,
#                                             egress=False,
#                                             protocol="-1",
#                                             rule_action="allow",
#                                             cidr_block='0.0.0.0/0',
#                                             from_port=0,
#                                             to_port=0)

#     private_acl_outbound = ec2.NetworkAclRule(f"private-acl-outbound-{i+1}",
#                                             network_acl_id=private_acl.id,
#                                             rule_number=200 + i*10,
#                                             egress=True,
#                                             protocol="-1",
#                                             rule_action="allow",
#                                             cidr_block='0.0.0.0/0',
#                                             from_port=0,
#                                             to_port=0)

# # # public
# public_acl = ec2.NetworkAcl("public-acl",
#                             vpc_id=vpc.id,
#                             subnet_ids=public_subnet_ids,
#                             tags=tags)

# public_acl_inbound = ec2.NetworkAclRule("public-acl-inbound",
#                                         network_acl_id=public_acl.id,
#                                         rule_number=100,
#                                         egress=False,
#                                         protocol="tcp",
#                                         rule_action="allow",
#                                         cidr_block="0.0.0.0/0",
#                                         from_port=80,
#                                         to_port=5000)

# public_acl_outbound = ec2.NetworkAclRule("public-acl-outbound",
#                                          network_acl_id=public_acl.id,
#                                          rule_number=100,
#                                          egress=True,
#                                          protocol="-1",
#                                          rule_action="allow",
#                                          cidr_block="0.0.0.0/0",
#                                          from_port=0,
#                                          to_port=0)


# SG
web_ui_lb_sg = ec2.SecurityGroup('web-ui-lb-sg',
                                 description='Allow inbound access from 80 for web-ui',
                                 vpc_id=vpc.id,
                                 ingress=[

                                     ec2.SecurityGroupIngressArgs(
                                         protocol='tcp',
                                         from_port=80,
                                         to_port=80,
                                         cidr_blocks=['0.0.0.0/0'],
                                     )
                                 ],
                                 egress=[
                                     ec2.SecurityGroupEgressArgs(
                                         protocol='-1',
                                         from_port=0,
                                         to_port=0,
                                         cidr_blocks=['0.0.0.0/0'],
                                     )
                                 ],
                                 tags=tags,
                                 )

web_ui_app_sg = ec2.SecurityGroup('web-ui-app-sg',
                                  description='Allow inbound access from 5000 for web-ui',
                                  vpc_id=vpc.id,
                                  ingress=[

                                      ec2.SecurityGroupIngressArgs(
                                          protocol='tcp',
                                          from_port=5000,
                                          to_port=5000,
                                          security_groups=[web_ui_lb_sg.id]
                                      )
                                  ],
                                  egress=[
                                      ec2.SecurityGroupEgressArgs(
                                          protocol='-1',
                                          from_port=0,
                                          to_port=0,
                                          cidr_blocks=['0.0.0.0/0'],
                                      )
                                  ],
                                  tags=tags,
                                  )

web_api_lb_sg = ec2.SecurityGroup('web-api-lb-sg',
                                  description='Allow inbound access from the public subnet',
                                  vpc_id=vpc.id,
                                  ingress=[
                                      ec2.SecurityGroupIngressArgs(
                                          protocol='tcp',
                                          from_port=5000,
                                          to_port=5000,
                                        cidr_blocks=public_subnet_cidr_blocks
                                        #   cidr_blocks=['0.0.0.0/0'],
                                      )
                                  ],
                                  egress=[
                                      ec2.SecurityGroupEgressArgs(
                                          protocol="-1",
                                          from_port=0,
                                          to_port=0,
                                          cidr_blocks=['0.0.0.0/0'],
                                      )
                                  ],
                                  tags=tags,
                                  )

web_api_app_sg = ec2.SecurityGroup('web-api-app-sg',
                                   description='Allow inbound access from the public subnet',
                                   vpc_id=vpc.id,
                                   ingress=[
                                       ec2.SecurityGroupIngressArgs(
                                           protocol='tcp',
                                           from_port=5000,
                                           to_port=5000,
                                           #    cidr_blocks=public_subnet_cidr_blocks+private_subnet_cidr_blocks
                                           security_groups=[web_api_lb_sg.id],
                                       )
                                   ],
                                   egress=[
                                       ec2.SecurityGroupEgressArgs(
                                           protocol="-1",
                                           from_port=0,
                                           to_port=0,
                                           cidr_blocks=['0.0.0.0/0'],
                                       )
                                   ],
                                   tags=tags,
                                   )



# Create the ECS Cluster
cluster_name = "web-cluster"
cluster = ecs.Cluster(cluster_name,
                      tags=tags,
                      settings=[
                          ecs.ClusterSettingArgs(
                              name="containerInsights",  # for debugging container
                              value="enabled"
                          )],

                      )

web_ui_target_group = lb.TargetGroup('web-ui-tg',
                                     port=5000,
                                     protocol='HTTP',
                                     target_type='ip',
                                     vpc_id=vpc.id,
                                     health_check={
                                         "enabled": True,
                                         "path": "/",  # health check path
                                         "interval": 30,
                                         "protocol": "HTTP",
                                         "matcher": "200"
                                     },
                                     tags=tags
                                     )
web_api_target_group = lb.TargetGroup('web-api-tg',
                                      port=5000,
                                      protocol='HTTP',
                                      target_type='ip',
                                      vpc_id=vpc.id,
                                      health_check={
                                          "enabled": True,
                                          "path": "/WeatherForecast",  # health check path
                                          "interval": 30,
                                          "protocol": "HTTP",
                                          "matcher": "200"
                                      },
                                      tags=tags
                                      )

# Create IAM role
task_exec_role = iam.Role('task-exec-role',
                          assume_role_policy={
                              'Version': '2012-10-17',
                              'Statement': [{
                                  'Action': 'sts:AssumeRole',
                                  'Principal': {
                                      'Service': 'ecs-tasks.amazonaws.com',
                                  },
                                  'Effect': 'Allow',
                                  'Sid': '',
                              }],
                          },
                          tags=tags
                          )


# Attach the AmazonECSTaskExecutionRolePolicy
iam.RolePolicyAttachment('ecs-policy-role-attachment',
                         role=task_exec_role.name,
                         policy_arn='arn:aws:iam::aws:policy/AmazonECS_FullAccess',
                         )

iam.RolePolicyAttachment('ecs-service-loadbalancer-role-attachment',
                         role=task_exec_role.name,
                         policy_arn='arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess'
                         )

iam.RolePolicyAttachment('ecs-ecr-role-attachment',
                         role=task_exec_role.name,
                         policy_arn='arn:aws:iam::110504524436:policy/ECRPoliciesFullAccess'
                         )

# Create the CloudWatch policy
cloudwatch_policy = iam.Policy('cloudwatchPolicy',
                               name='cloudwatchPolicy',
                               description="A policy that allows a task to create and manage CloudWatch logs",
                               policy=pulumi.Output.all().apply(lambda _: {
                                   'Version': '2012-10-17',
                                   'Statement': [
                                       {
                                           'Effect': 'Allow',
                                           'Action': [
                                               'logs:CreateLogGroup',
                                               'logs:CreateLogStream',
                                               'logs:PutLogEvents'
                                           ],
                                           'Resource': '*'
                                       }
                                   ]
                               })
                               )

iam.RolePolicyAttachment('ecs-cloudwatch-policy-attachment',
                         role=task_exec_role.name,
                         policy_arn=cloudwatch_policy.arn
                         )

web_ui_lb = lb.LoadBalancer(
    "web-ui-lb", security_groups=[web_ui_lb_sg.id], subnets=public_subnet_ids, internal=False, tags=tags)
web_api_lb = lb.LoadBalancer(
    "web-api-lb", security_groups=[web_api_lb_sg.id], subnets=private_subnet_ids, internal=True, tags=tags)


web_ui_listener = lb.Listener("web-ui-listener",
                              load_balancer_arn=web_ui_lb.arn,
                              port=80,
                              protocol="HTTP",
                              default_actions=[lb.ListenerDefaultActionArgs(
                                  type="forward",
                                  target_group_arn=web_ui_target_group.arn,
                              )], tags=tags)


web_api_listener = lb.Listener("web-api-listener",
                               load_balancer_arn=web_api_lb.arn,
                               port=5000,
                               protocol="HTTP",
                               default_actions=[lb.ListenerDefaultActionArgs(
                                   type="forward",
                                   target_group_arn=web_api_target_group.arn,
                               )], tags=tags)

# Create a new CloudWatch LogGroup
log_group = cloudwatch.LogGroup('containerLogGroup')

# Create a new ECS Task Definition
web_ui_container_definitions = pulumi.Output.all(web_ui_image.image_uri, web_api_lb.dns_name, log_group.name).apply(lambda args: json.dumps([{
    "name": "web-ui-container",
    "image": args[0],
    "environment": [{
        "name": "ApiAddress",
        "value": f"http://{args[1]}:5000/WeatherForecast"
    },
        #     {
        #     "name": "ASPNETCORE_ENVIRONMENT",
        #     "value": "Development"
        # }
    ],
    "cpu": 256,
    "memory": 512,
    "portMappings": [{
        "containerPort": 5000,
        "hostPort": 5000,
        "protocol": "tcp"
    }],
    "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": args[2],
            "awslogs-region": "us-east-2",
            "awslogs-stream-prefix": "web"
        }
    },
}]))

web_api_container_definitions = pulumi.Output.all(web_api_image.image_uri, log_group.name).apply(lambda args: json.dumps([{
    "name": "web-api-container",
    "image": args[0],
    "environment": [
        {
            "name": "ASPNETCORE_ENVIRONMENT",
            "value": "Development"
        }
    ],
    "cpu": 256,
    "memory": 512,
    "portMappings": [{
        "containerPort": 5000,
        "hostPort": 5000,
        "protocol": "tcp"
    }],
    "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": args[1],
            "awslogs-region": "us-east-2",
            "awslogs-stream-prefix": "web"
        }
    },

}]))

web_ui_task_definition = ecs.TaskDefinition(
    "web_ui-app-task",
    family="fargate-task-definition",
    cpu="512",
    memory="1024",
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=task_exec_role.arn,
    container_definitions=web_ui_container_definitions
)
web_api_task_definition = ecs.TaskDefinition(
    "web_api-app-task",
    family="fargate-task-definition",
    cpu="512",
    memory="1024",
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=task_exec_role.arn,
    container_definitions=web_api_container_definitions
)

# Specify the ECS service
web_ui_service = ecs.Service(
    "web-ui-svc",
    cluster=cluster.arn,
    desired_count=2,
    launch_type="FARGATE",
    task_definition=web_ui_task_definition.arn,
    network_configuration={
        "assign_public_ip": "true",
        "subnets": public_subnet_ids,
        "security_groups": [web_ui_app_sg.id]
    },
    load_balancers=[{
        "target_group_arn": web_ui_target_group.arn,
        "container_name": "web-ui-container",
        "container_port": 5000
    }],
    deployment_maximum_percent=200,
    deployment_minimum_healthy_percent=50,
    opts=pulumi.ResourceOptions(depends_on=[web_ui_listener]),
    health_check_grace_period_seconds=10,
    tags=tags
)


web_api_service = ecs.Service(
    "web-api-svc",
    cluster=cluster.arn,
    desired_count=2,
    launch_type="FARGATE",
    task_definition=web_api_task_definition.arn,
    network_configuration={
        "subnets": private_subnet_ids,
        "security_groups": [web_api_app_sg.id]
    },
    load_balancers=[{
        "target_group_arn": web_api_target_group.arn,
        "container_name": "web-api-container",
        "container_port": 5000
    }],
     deployment_maximum_percent=200,
    deployment_minimum_healthy_percent=50,
    opts=pulumi.ResourceOptions(depends_on=[web_api_listener]),
    health_check_grace_period_seconds=10,
    tags=tags
)


pulumi.export("api-lb-url", pulumi.Output.concat(
    "http://", web_api_lb.dns_name))

pulumi.export("web-lb-url", pulumi.Output.concat(
    "http://", web_ui_lb.dns_name))

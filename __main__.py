"""A Python Pulumi program"""

import pulumi

from pulumi import Output, export, get_stack
from pulumi_aws import Provider, ecr, ecs, ec2, lb, get_availability_zones, autoscaling, iam
import pulumi_awsx as awsx
import json

azs = get_availability_zones(state="available")

# Define shared tags
stack_name = get_stack()
tags = {
    'environment': 'dev',
    'stack_name': stack_name,
}

# Create the ECR Repositories for web-api and web-ui
web_ui_repo = awsx.ecr.Repository('web-ui-repo', tags=tags, force_delete=True)
web_api_repo = awsx.ecr.Repository('web-api-repo', tags=tags, force_delete=True)

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
vpc = ec2.Vpc(stack_name+"-vpc", cidr_block="10.3.0.0/16", tags=tags)

igw = ec2.InternetGateway("igw", vpc_id=vpc.id, tags=tags)

public_route_table = ec2.RouteTable("public-route-table", vpc_id=vpc.id, routes=[
                                    ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", gateway_id=igw.id)], tags=tags)

public_subnet_ids = []
private_subnet_ids = []
# Create a public subnet within the VPC
for i, az in enumerate(azs.names, 1):
    if i > 2: # only create 2 subnets in 2 AZs
        break

    # public subnet
    public_subnet = ec2.Subnet(f"public-subnet-{i}",
                               cidr_block=f"10.3.1.{i*64}/26",
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
    private_subnet = ec2.Subnet(f"private-subnet-{i}",
                                vpc_id=vpc.id,
                                cidr_block=f"10.3.2.{i*64}/26",
                                availability_zone=az,
                                tags=tags
                                )
    private_subnet_ids.append(private_subnet.id)
    private_route_table = ec2.RouteTable(f"private-route-table-{i}", vpc_id=vpc.id, routes=[
                                         ec2.RouteTableRouteArgs(cidr_block="0.0.0.0/0", nat_gateway_id=nat_gateway.id)], tags=tags)

    private_route_table_associaition = ec2.RouteTableAssociation(
        f"private-subnet-association-{i}", route_table_id=private_route_table.id, subnet_id=private_subnet.id)

    # # Create a Network ACL TBC
  

web_ui_sg = ec2.SecurityGroup('web-ui-sg',
                              description='Allow inbound access from anywhere for web-ui',
                              vpc_id=vpc.id,
                              ingress=[
                                  ec2.SecurityGroupIngressArgs(
                                      protocol='-1',
                                      from_port=0,
                                      to_port=0,
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

# Define the security group for the public subnet
web_api_sg = ec2.SecurityGroup('web-api-sg',
                               description='Allow inbound access from the public subnet',
                               vpc_id=vpc.id,
                               ingress=[
                                   ec2.SecurityGroupIngressArgs(
                                       protocol='-1',       # Allow TCP traffic
                                       from_port=0,         # From port 80
                                       to_port=0,           # To port 80
                                    #    cidr_blocks=[vpc.cidr_block]
                                        cidr_blocks=['0.0.0.0/0'],
                                   )
                               ],
                               egress=[
                                   ec2.SecurityGroupEgressArgs(
                                       protocol="-1",      # '-1' indicates all protocols
                                       from_port=0,
                                       to_port=0,
                                       # Allow outbound traffic to all IPs
                                       cidr_blocks=['0.0.0.0/0'],
                                   )
                               ],
                               tags=tags,
                               )

cluster_name = "web-cluster"

# Create the ECS Cluster
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

# # Create IAM role
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

web_ui_lb = lb.LoadBalancer(
    "web-ui-lb", security_groups=[web_ui_sg.id], subnets=public_subnet_ids, tags=tags)
web_api_lb = lb.LoadBalancer(
    "web-api-lb", security_groups=[web_api_sg.id], subnets=private_subnet_ids, tags=tags)


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

web_ui_container_definitions = pulumi.Output.all(web_ui_image.image_uri, web_api_lb.dns_name).apply(lambda args: json.dumps([{
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
    # "healthCheck": {
    #     "command":  ["CMD-SHELL", "curl -f http://localhost:5000/ || exit 1"],
    #     "interval": 30,
    #     "timeout": 5,
    #     "retries": 3,
    #     "startPeriod": 40
    # }

}]))

web_api_container_definitions = web_api_image.image_uri.apply(lambda image_uri: json.dumps([{
    "name": "web-api-container",
    "image": image_uri,
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
        "security_groups": [web_ui_sg.id]
    },
    load_balancers=[{
        "target_group_arn": web_ui_target_group.arn,
        "container_name": "web-ui-container",
        "container_port": 5000
    }],
    opts=pulumi.ResourceOptions(depends_on=[web_ui_listener]),
    health_check_grace_period_seconds=10,
    tags=tags
)

# Specify the ECS service
web_api_service = ecs.Service(
    "web-api-svc",
    cluster=cluster.arn,
    desired_count=2,
    launch_type="FARGATE",
    task_definition=web_api_task_definition.arn,
    network_configuration={
        "subnets": private_subnet_ids,
        "security_groups": [web_api_sg.id]
    },
    load_balancers=[{
        "target_group_arn": web_api_target_group.arn,
        "container_name": "web-api-container",
        "container_port": 5000
    }],
    opts=pulumi.ResourceOptions(depends_on=[web_api_listener]),
    health_check_grace_period_seconds=10,
    tags=tags
)

pulumi.export("url", pulumi.Output.concat(
    "http://", web_ui_lb.dns_name))

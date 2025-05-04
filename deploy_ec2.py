import boto3
import os
from botocore.exceptions import ClientError
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EC2Manager:
    def __init__(self):
        self.ec2_client = boto3.client(
            'ec2',
            aws_access_key_id=os.getenv('MY_AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('MY_AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('MY_AWS_REGION')
        )
        self.ec2_resource = boto3.resource(
            'ec2',
            aws_access_key_id=os.getenv('MY_AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('MY_AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('MY_AWS_REGION')
        )

    def create_security_group(self):
        """Create a security group for the EC2 instance"""
        try:
            security_group = self.ec2_client.create_security_group(
                GroupName='WordToPDFConverter-SG',
                Description='Security group for Word to PDF Converter'
            )
            
            # Add inbound rules
            self.ec2_client.authorize_security_group_ingress(
                GroupId=security_group['GroupId'],
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 80,
                        'ToPort': 80,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 443,
                        'ToPort': 443,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    },
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            
            logger.info(f"Created security group: {security_group['GroupId']}")
            return security_group['GroupId']
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidGroup.Duplicate':
                # Get existing security group
                security_groups = self.ec2_client.describe_security_groups(
                    GroupNames=['WordToPDFConverter-SG']
                )
                return security_groups['SecurityGroups'][0]['GroupId']
            else:
                logger.error(f"Error creating security group: {str(e)}")
                raise

    def create_instance(self):
        """Create and launch an EC2 instance"""
        try:
            # Create security group
            security_group_id = self.create_security_group()
            
            # Create instance
            instances = self.ec2_resource.create_instances(
                ImageId='ami-0989fb15ce71ba39e',  # Amazon Linux 2 AMI ID
                MinCount=1,
                MaxCount=1,
                InstanceType='t2.micro',
                KeyName=os.getenv('EC2_KEY_PAIR_NAME', 'word-to-pdf-converter-key'),
                SecurityGroupIds=[security_group_id],
                UserData='''#!/bin/bash
                    yum update -y
                    yum install -y python3-pip
                    yum install -y git
                    cd /home/ec2-user
                    git clone https://github.com/yourusername/word-to-pdf-converter.git
                    cd word-to-pdf-converter
                    pip3 install -r requirements.txt
                    python3 app.py
                ''',
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {
                                'Key': 'Name',
                                'Value': 'WordToPDFConverter'
                            }
                        ]
                    }
                ]
            )
            
            instance = instances[0]
            logger.info(f"Created EC2 instance: {instance.id}")
            
            # Wait for instance to be running
            instance.wait_until_running()
            
            # Get instance public IP
            instance.load()
            public_ip = instance.public_ip_address
            logger.info(f"Instance is running at: {public_ip}")
            
            return instance.id, public_ip
            
        except ClientError as e:
            logger.error(f"Error creating EC2 instance: {str(e)}")
            raise

    def terminate_instance(self, instance_id):
        """Terminate an EC2 instance"""
        try:
            instance = self.ec2_resource.Instance(instance_id)
            response = instance.terminate()
            logger.info(f"Terminated instance: {instance_id}")
            return response
        except ClientError as e:
            logger.error(f"Error terminating instance: {str(e)}")
            raise

if __name__ == '__main__':
    # Create EC2 manager
    ec2_manager = EC2Manager()
    
    try:
        # Create new instance
        instance_id, public_ip = ec2_manager.create_instance()
        print(f"""
        EC2 Instance successfully created!
        Instance ID: {instance_id}
        Public IP: {public_ip}
        
        Your application will be available at: http://{public_ip}
        Allow a few minutes for the instance to complete setup.
        
        To SSH into the instance:
        ssh -i your-key-pair.pem ec2-user@{public_ip}
        """)
    except Exception as e:
        print(f"Failed to create EC2 instance: {str(e)}") 
sudo apt-get install software-properties-common
sudo apt-add-repository universe
sudo apt-get update
sudo apt install python3-pip
pip3 install torch
pip3 install transformers
pip3 install numpy
pip3 install torch_optimizer
pip3 install pandas
export SM_MODEL_DIR='.'
export SM_CHANNEL_DATA='~/.'
export SM_NUM_GPUS=0
export SM_NUM_CPUS=2
#wget s3://sagemaker-eu-west-1-016401055034/pytorch-training-210304-1751-001-3b6fc0d3/output/model.tar.gz
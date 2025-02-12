import logging
import os.path

import pandas as pd
import yaml
import random
import numpy as np
import torch.nn
from torch.utils.data import random_split, DataLoader
from phd_experiments.ttode2.models import LearnableOde, ProjectionModel, OutputModel, OdeSolverModel, NNodeFunc, \
    TensorTrainOdeFunc
from phd_experiments.ttode2.utils import get_dataset, get_solver, get_ode_func, get_tensor_dtype, \
    get_activation, get_loss_function, get_logger, assert_models_learnability
from datetime import datetime
from tqdm import tqdm

"""
some material

stability of linear ode
https://physiology.med.cornell.edu/people/banfelder/qbio/resources_2010/2010_4.2%20Stability%20and%20Linearization%20of%20ODEs.pdf
https://www.cs.princeton.edu/courses/archive/fall11/cos323/notes/cos323_f11_lecture19_pde2.pdf
https://faculty.ksu.edu.sa/sites/default/files/stability.pdf
"""

"""
Objective of this script is to verify on research hypothesis ( Tensor-Neural ODE expressive power , no focus on
memory or speed 
dzdt = A.phi([z,t]) that works with complex problems
"""

EXPERIMENTS_LOG_DIR = "./experiments_log"
EXPERIMENTS_COUNTER_FILE = "./experiment_counter.txt"
PANDAS_MAX_DISPLAY_ROW = 1000
LOG_FORMAT = "[%(filename)s:%(lineno)s - %(funcName)10s()] %(asctime)s %(levelname)s %(message)s"
DATE_TIME_FORMAT = "%Y-%m-%d:%H:%M:%S"


def y_hat_backward_hook(grad):
    pass


def save_ode_func_model(ode_func_model: torch.nn.Module, experiment_number: int, tstamp: str, model_dir: str):
    model_type = None
    if isinstance(ode_func_model, NNodeFunc):
        model_type = "ode_func_nn"
    elif isinstance(ode_func_model, TensorTrainOdeFunc):
        model_type = "ode_func_tt"
    model_file_path = os.path.join(model_dir, f"{model_type}_experiment_no_{experiment_number}_{tstamp}.model")
    torch.save(ode_func_model, model_file_path)


if __name__ == '__main__':
    tstamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
    # set pandas config
    pd.set_option('display.max_rows', PANDAS_MAX_DISPLAY_ROW)
    # load configs
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
    # get logger
    logger, experiment_number = get_logger(level=config['train']['log-level'],
                                           date_time_format=DATE_TIME_FORMAT, log_format=LOG_FORMAT,
                                           experiments_counter_file_path=EXPERIMENTS_COUNTER_FILE,
                                           experiments_log_dir=EXPERIMENTS_LOG_DIR)
    logger.info(f"This is Learnable-Ode training Script")
    # set seed
    seed = config['train']['seed']
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    # get dataset and loader
    overall_dataset = get_dataset(config)
    input_dim = overall_dataset.get_input_dim()
    output_dim = overall_dataset.get_output_dim()
    splits = random_split(dataset=overall_dataset,
                          lengths=[config["train"]["ratio"], 1 - config["train"]["ratio"]])
    train_dataset = splits[0]
    test_dataset = splits[1]
    train_loader = DataLoader(dataset=train_dataset, batch_size=config["train"]["batch_size"],
                              shuffle=config["train"]["shuffle"])
    # test_loader = DataLoader(dataset=test_dataset, batch_size=config["train"]["batch_size"],
    #                          shuffle=config["train"]["shuffle"])

    # get ode-solver-model
    solver = get_solver(config=config)
    latent_dim = config["container"]["latent-dim"]
    # FIXME remove and test Dz>Dx
    assert latent_dim == input_dim, "latent-dim must == input-dim, for now"
    ode_func = get_ode_func(config=config)
    ode_solver_model = OdeSolverModel(solver=solver, ode_func=ode_func, t_span=config['ode']['solver']['t-span'])
    # get projection-model
    projection_model_activation = get_activation(activation_name=config['projection']['activation'])
    projection_model = ProjectionModel(Dx=input_dim, Dz=latent_dim,
                                       activation_module=projection_model_activation,
                                       unif_low=config['init']['uniform']['low'],
                                       unif_high=config['init']['uniform']['high'],
                                       learnable=config['projection']['learnable'])
    # get output-model
    output_activation_model = get_activation(activation_name=config['output']['activation'])
    output_model = OutputModel(Dz=latent_dim, Dy=output_dim, activation_module=output_activation_model,
                               learnable=config['output']['learnable'],
                               linear_weight_full_value=config['output']['full'])
    # assert learnability to be as configured
    assert_models_learnability(config=config, projection_model=projection_model, output_model=output_model)
    # get-model
    tensor_dtype = get_tensor_dtype(config=config)
    model = LearnableOde(projection_model=projection_model, ode_solver_model=ode_solver_model,
                         output_model=output_model)
    loss_fn = get_loss_function(loss_name=config['train']['loss'])
    optimizer = torch.optim.SGD(params=model.parameters(), lr=config['train']['lr'])
    logger.info(f"ODE-FUNC Model = {type(ode_func)} , learnable-numel = {ode_func.num_learnable_scalars()}")
    logger.info(f"Running with config : \n "
                f"{config}"
                f"\n"
                f"============="
                f"\n")
    start_time = datetime.now()
    epoch_no_list = []
    epoch_avg_loss = []
    if logger.level == logging.DEBUG:
        ode_func_params_vec = ode_func.flatten().clone()
    for epoch in tqdm(range(config['train']['epochs']), desc="epochs"):
        batches_losses = []
        for i, (X, y) in enumerate(train_loader):
            optimizer.zero_grad()
            y_hat = model(X)
            # y_hat = torch.nan_to_num(input=y_hat, nan=0.01)
            y_hat.register_hook(y_hat_backward_hook)
            residual = loss_fn(y_hat, y)
            loss = residual
            batches_losses.append(residual.item())
            loss.backward()
            # debug gradient of ode-func
            if logger.level == logging.DEBUG:
                ode_func_grad_vec = ode_func.flat_gradients()
                ode_func_params_vec_new = ode_func.flatten().clone()
                delta_ode_func_params_vec = ode_func_params_vec_new - ode_func_params_vec
                ode_func_params_vec = ode_func_params_vec_new
            # logger.debug(f'Epoch {epoch}, batch {i} => loss = {loss.item()}')
            optimizer.step()
            # TODO add core orthog. step
            #   https://arxiv.org/pdf/2101.09184.pdf p 5 last two lines
        if epoch % config['train']['epochs_block'] == 0:
            epoch_no_list.append(epoch)
            epoch_avg_loss.append(np.nanmean(batches_losses))
            logger.info(f"\t epoch # {epoch} : loss = {np.nanmean(batches_losses)}")
            # logger.debug(f'\nEpoch # {epoch} =>'
            #              f'Gradients-norm sum of ode_func of type {type(ode_func)} = '
            #              f'{ode_func.gradients_sum_norm()}')
    end_time = datetime.now()
    epochs_losses_df = pd.DataFrame({'epoch': epoch_no_list, 'loss': epoch_avg_loss})
    logger.info(f'\n{epochs_losses_df}\n')
    logger.info(f'Training-Time = {(end_time - start_time).seconds} seconds')
    logger.info(f'Experiment info is logged under experiment # {experiment_number}')

    ###
    if config['ode']['model'] == "nn" and config['ode']['nn']['save']:
        save_ode_func_model(ode_func_model=ode_func, experiment_number=experiment_number, tstamp=tstamp,
                            model_dir=config["train"]["models_dir"])

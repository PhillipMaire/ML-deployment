import tensorflow as tf
import optuna
import os
import mlflow
import pandas as pd
import time
from dotenv import load_dotenv
# Project Imports
from steps.load_step import load
from steps.preprocess_step import preprocess
from steps.model_step import model
from steps import utils

load_dotenv()

if __name__ == "__main__":
    # arg parser for local
    optuna_study_name = "mnist-hyperparam-local"

    # preprocess and define batch sizes for tensorflow 
    ds_train = load.load_tensorflow_dataset_production('mnist')
    ds_train = ds_train.map(preprocess.preprocess_mnist_tfds, 
                            num_parallel_calls=tf.data.AUTOTUNE)
    ds_train = ds_train.batch(128)

    # instantiate model
    mnist_model = model.MNIST()

    # mlflow experiment
    experiment_id = utils.set_mlflow_experiment(experiment_name=optuna_study_name)
    
    # load params from optuna
    optuna_storage_url="postgresql://{}:{}@localhost:5433/{}".format(
                os.environ["POSTGRES_USER"],
                os.environ["POSTGRES_PASSWORD"],
                os.environ["POSTGRES_OPTUNA_DB"]
            )
    print('loading study...')
    study = optuna.load_study(
        study_name=optuna_study_name,
        storage=optuna_storage_url,
    )  
    hyperparameters = study.best_params

    # train model and log via mlflow
    current = pd.to_datetime('now')
    mlflow_run_name=f'production-{time.strftime("%Y%m%d-%H%M%S")}'
    with mlflow.start_run(experiment_id=experiment_id,  
                            run_name=mlflow_run_name) as run:
        mnist_model.fit_production(xy_train=ds_train,
                                    hyperparameters=hyperparameters)
        # MLFlow Tracking parameters
        mlflow.log_params(params=hyperparameters)

        # MLFlow Tracking metrics 
        # Logging metrics for each epoch (housed in dictionary)
        training_history = mnist_model._train_history.history
        for epoch in range(0, hyperparameters['epochs']):
            insert = {}
            for metric, value in training_history.items():
                insert[metric] = training_history[metric][epoch]
            mlflow.log_metrics(metrics=insert, step=epoch+1)

        # MLFlow tracking artifact (e.g. model file)
        # this will log the model and all its details under run_id/artifacts
        # ths will also register the model so it can be served
        mlflow.pyfunc.log_model(python_model=mnist_model,
                                artifact_path="",
                                registered_model_name=optuna_study_name)

        # Close out MLFlow run to prevent any log contamination.
        mlflow.end_run(status='FINISHED') 

    


    
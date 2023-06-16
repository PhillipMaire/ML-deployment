import os
import tensorflow as tf
import optuna
from optuna.integration.mlflow import MLflowCallback
# Project Imports
from steps.load_step import load
from steps.preprocess_step import preprocess
from steps.model_step import model
from steps import utils


# hyperparameters search using Optuna
# can scale Optuna with Kubernetes https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/004_distributed.html
def objective(trial): 
    """
    Optuna objective function for tuning transfer learning model
    """
    hyperparams = {
        'learning_rate': trial.suggest_float('learning_rate', 0.00001, 0.1, log=True),
        'l1': trial.suggest_float('l1', 0.0, 0.05),
        'l2': trial.suggest_float('l2', 0.0, 0.05),
        'num_hidden': trial.suggest_int('num_hidden', 8, 64),
        'epochs': trial.suggest_int('epochs', 1, 3)
    }

    mnist_model = model.MNIST()
    mnist_model.fit_hp_search(ds_train, ds_test, hyperparams)
    training_history = mnist_model._train_history.history
    validation_accuracy = training_history['val_accuracy'][-1]
    return validation_accuracy



if __name__ == "__main__":
    # preprocess and define batch sizes for tensorflow 
    ds_train, ds_test = load.load_tensorflow_dataset('mnist')
    ds_train = ds_train.map(preprocess.preprocess_mnist_tfds, num_parallel_calls=tf.data.AUTOTUNE)
    ds_train = ds_train.batch(128)
    ds_test = ds_test.map(preprocess.preprocess_mnist_tfds, num_parallel_calls=tf.data.AUTOTUNE)
    ds_test = ds_test.batch(128) 


    # define optuna variables
    optuna_study_name = "mnist-hyperparam-optuna-docker"
    # optuna_storage_url="postgresql://{}:{}@{}:5432/{}".format(
    #             os.environ["POSTGRES_USER"],
    #             os.environ["POSTGRES_PASSWORD"],
    #             os.environ["POSTGRES_OPTUNA_HOSTNAME"],
    #             os.environ["POSTGRES_OPTUNA_DB"]
    #         )
    POSTGRES_DB="optunadb"
    POSTGRES_USER="postgres"
    POSTGRES_PASSWORD="mysecretpassword"
    POSTGRES_HOSTNAME="localhost"
    optuna_storage_url="postgresql://{}:{}@{}:5432/{}".format(
            POSTGRES_USER,
            POSTGRES_PASSWORD,
            POSTGRES_HOSTNAME,
            POSTGRES_DB
            )

    # create or load optuna study
    try:
        print('loading study...')
        study = optuna.load_study(
            study_name=optuna_study_name,
            storage=optuna_storage_url,
        )  
    except KeyError:
        print('no study found. building from scratch...')
        study = optuna.create_study(
            study_name=optuna_study_name,
            storage=optuna_storage_url,
            pruner=optuna.pruners.HyperbandPruner(),
            direction='maximize')


    # create or set an experiment for optuna. Each trial from Optuna is logged as one run in an MLFlow experiment.
    os.environ["MLFLOW_TRACKING_URI"] = "postgresql+psycopg2://postgres:mysecretpassword@localhost:5432/mlflowdb"
    experiment_id = utils.set_mlflow_experiment(experiment_name=optuna_study_name)
    mlflow_kwargs = {'experiment_id': experiment_id}

    # a new experiment name will be created in MLFlow using the Optuna study name
    study.optimize(objective,
                n_trials=2,
                n_jobs=2,
                callbacks=[MLflowCallback(metric_name="val_accuracy",
                                            create_experiment=False,
                                            mlflow_kwargs=mlflow_kwargs)]
                )
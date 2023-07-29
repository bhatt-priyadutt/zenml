---
description: Using materializers to pass custom data types through steps.
---

# Handle custom data types

A ZenML pipeline is built in a data-centric way. The outputs and inputs of steps define how steps are connected and the order in which they are executed. Each step should be considered as its very own process that reads and writes its inputs and outputs from and to the [artifact store](../../component-guide/artifact-stores/artifact-stores.md). This is where **materializers** come into play.

A materializer dictates how a given artifact can be written to and retrieved from the artifact store and also contains all serialization and deserialization logic. Whenever you pass artifacts as outputs from one pipeline step to other steps as inputs, the corresponding materializer for the respective data type defines how this artifact is first serialized and written to the artifact store, and then deserialized and read in the next step.

{% hint style="info" %}
ZenML already includes built-in materializers for many common data types. However, if you want to pass custom objects between pipeline steps, these objects are by default saved using [cloudpickle](https://github.com/cloudpipe/cloudpickle) , which is not production-ready because the resulting artifacts cannot be loaded when running with a different Python version. In such cases, you should consider building a custom Materializer to save your objects in a more robust and efficient format.
{% endhint %}

## Custom materializers

#### Base implementation

Before we dive into how custom materializers can be built, let us briefly discuss how materializers in general are implemented. In the following, you can see the implementation of the abstract base class `BaseMaterializer`, which defines the interface of all materializers:

```python
class BaseMaterializer(metaclass=BaseMaterializerMeta):
    """Base Materializer to realize artifact data."""

    ASSOCIATED_ARTIFACT_TYPE = ArtifactType.BASE
    ASSOCIATED_TYPES = ()

    def __init__(self, uri: str):
        """Initializes a materializer with the given URI."""
        self.uri = uri

    def load(self, data_type: Type[Any]) -> Any:
        """Write logic here to load the data of an artifact.

        Args:
            data_type: The type of data that the artifact should be loaded as.

        Returns:
            The data of the artifact.
        """
        # read from a location inside self.uri
        # 
        # Example:
        # data_path = os.path.join(self.uri, "abc.json")
        # return yaml_utils.read_json(data_path)
        ...

    def save(self, data: Any) -> None:
        """Write logic here to save the data of an artifact.

        Args:
            data: The data of the artifact to save.
        """
        # write `data` into self.uri
        # 
        # Example:
        # data_path = os.path.join(self.uri, "abc.json")
        # yaml_utils.write_json(data_path, data)
        ...

    def save_visualizations(self, data: Any) -> Dict[str, VisualizationType]:
        """Save visualizations of the given data.

        Args:
            data: The data of the artifact to visualize.

        Returns:
            A dictionary of visualization URIs and their types.
        """
        # Optionally, define some visualizations for your artifact
        #
        # E.g.:
        # visualization_uri = os.path.join(self.uri, "visualization.html")
        #
        # with fileio.open(visualization_uri, "w") as f:
        #     f.write("<html><body>data</body></html>")
        #
        # visualization_uri_2 = os.path.join(self.uri, "visualization.png")
        # data.save_as_png(visualization_uri_2)
        # return {
        #     visualization_uri: ArtifactVisualizationType.HTML,
        #     visualization_uri_2: ArtifactVisualizationType.IMAGE
        # }
        ...

    def extract_metadata(self, data: Any) -> Dict[str, "MetadataType"]:
        """Extract metadata from the given data.

        This metadata will be tracked and displayed alongside the artifact.

        Args:
            data: The data to extract metadata from.

        Returns:
            A dictionary of metadata.
        """
        # Optionally, extract some metadata from `data` for ZenML to store.
        #
        # Example:
        # return {
        #     "some_attribute_i_want_to_track": self.some_attribute,
        #     "pi": 3.14,
        # }
        ...
```

#### Handled data types

Each materializer has an `ASSOCIATED_TYPES` attribute that contains a list of data types that this materializer can handle. ZenML uses this information to call the right materializer at the right time. I.e., if a ZenML step returns a `pd.DataFrame`, ZenML will try to find any materializer that has `pd.DataFrame` in its `ASSOCIATED_TYPES`. List the data type of your custom object here to link the materializer to that data type.

#### The type of the generated artifact

Each materializer also has an `ASSOCIATED_ARTIFACT_TYPE` attribute, which defines what `zenml.enums.ArtifactType` is assigned to this data.

In most cases, you should choose either `ArtifactType.DATA` or `ArtifactType.MODEL` here. If you are unsure, just use `ArtifactType.DATA`. The exact choice is not too important, as the artifact type is only used as a tag in some of ZenML's visualizations.

#### Target location to store the artifact

Each materializer has a `uri` attribute, which is automatically created by ZenML whenever you run a pipeline and points to the directory of a file system where the respective artifact is stored (some location in the artifact store).

#### Storing and retrieving the artifact

The `load()` and `save()` methods define the serialization and deserialization of artifacts.

* `load()` defines how data is read from the artifact store and deserialized,
* `save()` defines how data is serialized and saved to the artifact store.

You will need to override these methods according to how you plan to serialize your objects. E.g., if you have custom PyTorch classes as `ASSOCIATED_TYPES`, then you might want to use `torch.save()` and `torch.load()` here.

### (Optional) How to Visualize the Artifact

Optionally, you can override the `save_visualizations()` method to automatically save visualizations for all artifacts saved by your materializer. These visualizations are then shown next to your artifacts in the dashboard:

![Evidently Artifact Visualization Example](../../../.gitbook/assets/artifact\_visualization\_dashboard.png)

Currently, artifacts can be visualized either as CSV table, embedded HTML, image or Markdown. For more information, see [zenml.enums.VisualizationType](https://github.com/zenml-io/zenml/blob/main/src/zenml/enums.py).

To create visualizations, you need to:

1. Compute the visualizations based on the artifact
2. Save all visualizations to paths inside `self.uri`
3. Return a dictionary mapping visualization paths to visualization types.

As an example, check out the implementation of the [zenml.materializers.NumpyMaterializer](https://github.com/zenml-io/zenml/blob/main/src/zenml/materializers/numpy\_materializer.py) that use matplotlib to automatically save or plot certain arrays.

### (Optional) Which Metadata to Extract for the Artifact

Optionally, you can override the `extract_metadata()` method to track custom metadata for all artifacts saved by your materializer. Anything you extract here will be displayed in the dashboard next to your artifacts.

To extract metadata, define and return a dictionary of values you want to track. The only requirement is that all your values are built-in types ( like `str`, `int`, `list`, `dict`, ...) or among the special types defined in [zenml.metadata.metadata\_types](https://github.com/zenml-io/zenml/blob/main/src/zenml/metadata/metadata\_types.py) that are displayed in a dedicated way in the dashboard. See [zenml.metadata.metadata\_types.MetadataType](https://github.com/zenml-io/zenml/blob/main/src/zenml/metadata/metadata\_types.py) for more details.

By default, this method will only extract the storage size of an artifact, but you can override it to track anything you wish. E.g., the [zenml.materializers.NumpyMaterializer](https://github.com/zenml-io/zenml/blob/main/src/zenml/materializers/numpy\_materializer.py) overrides this method to track the `shape`, `dtype`, and some statistical properties of each `np.ndarray` that it saves.

{% hint style="info" %}
If you would like to disable artifact visualization altogether, you can set `enable_artifact_visualization` at either pipeline or step level via `@pipeline(enable_artifact_visualization=False)` or `@step(enable_artifact_visualization=False)`.
{% endhint %}

#### (Optional) Which Metadata to Extract for the Artifact

Optionally, you can override the `extract_metadata()` method to track custom metadata for all artifacts saved by your materializer. Anything you extract here will be displayed in the dashboard next to your artifacts.

To extract metadata, define and return a dictionary of values you want to track. The only requirement is that all your values are built-in types ( like `str`, `int`, `list`, `dict`, ...) or among the special types defined in [src.zenml.metadata.metadata\_types](https://github.com/zenml-io/zenml/blob/main/src/zenml/metadata/metadata\_types.py) that are displayed in a dedicated way in the dashboard. See [src.zenml.metadata.metadata\_types.MetadataType](https://github.com/zenml-io/zenml/blob/main/src/zenml/metadata/metadata\_types.py) for more details.

By default, this method will only extract the storage size of an artifact, but you can overwrite it to track anything you wish. E.g., the `zenml.materializers.NumpyMaterializer` overwrites this method to track the `shape`, `dtype`, and some statistical properties of each `np.ndarray` that it saves.

{% hint style="info" %}
If you would like to disable artifact metadata extraction altogether, you can set `enable_artifact_metadata` at either pipeline or step level via `@pipeline(enable_artifact_metadata=False)` or `@step(enable_artifact_metadata=False)`.
{% endhint %}

## Usage

ZenML automatically scans your source code for definitions of materializers and registers them for the corresponding data type, so just having a custom materializer definition in your code is enough to enable the respective data type to be used in your pipelines.

Alternatively, you can also explicitly define which materializer to use for a specific step:

```python
@step(output_materializers=MyMaterializer)
def my_first_step(...) -> ...:
    ...
```

or you can use the `configure()` method of the step. E.g.:

```python
my_first_step.configure(output_materializers=MyMaterializer)
```

When there are multiple outputs, a dictionary of type `{<OUTPUT_NAME>: <MATERIALIZER_CLASS>}` can be supplied to the decorator or the `.configure(...)` method.

#### Configuring materializers at runtime

As briefly outlined in the [Runtime Configuration](configure-steps-pipelines.md) section, which materializer to use for the output of what step can also be configured within YAML config files.

For each output of your steps, you can define custom materializers to handle the loading and saving. You can configure them like this in the config:

```yaml
...
steps:
  <STEP_NAME>:
    ...
    outputs:
      <OUTPUT_NAME>:
        materializer_source: run.MyMaterializer
```

Check out [this page](../pipelining-features/configure-steps-pipelines.md#step-output-names) for information on your step output names and how to customize them.

## Basic example

Let's see how materialization works with a basic example. Let's say you have a custom class called `MyObject` that flows between two steps in a pipeline:

```python
import logging
from zenml import step, pipeline


class MyObj:
    def __init__(self, name: str):
        self.name = name


@step
def my_first_step() -> MyObj:
    """Step that returns an object of type MyObj."""
    return MyObj("my_object")


@step
def my_second_step(my_obj: MyObj) -> None:
    """Step that logs the input object and returns nothing."""
    logging.info(
        f"The following object was passed to this step: `{my_obj.name}`"
    )


@pipeline
def first_pipeline():
    output_1 = my_first_step()
    my_second_step(output_1)


first_pipeline()
```

Running the above without a custom materializer will work but print the following warning:

`No materializer is registered for type MyObj, so the default Pickle materializer was used. Pickle is not production ready and should only be used for prototyping as the artifacts cannot be loaded when running with a different Python version. Please consider implementing a custom materializer for type MyObj according to the instructions at https://docs.zenml.io/user-guide/advanced-guide/artifact-management/handle-custom-data-types`

To get rid of this warning and make our pipeline more robust, we will subclass the `BaseMaterializer` class, listing `MyObj` in `ASSOCIATED_TYPES`, and overwriting `load()` and `save()`:

```python
import os
from typing import Type

from zenml.enums import ArtifactType
from zenml.io import fileio
from zenml.materializers.base_materializer import BaseMaterializer


class MyMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (MyObj,)
    ASSOCIATED_ARTIFACT_TYPE = ArtifactType.DATA

    def load(self, data_type: Type[MyObj]) -> MyObj:
        """Read from artifact store."""
        with fileio.open(os.path.join(self.uri, 'data.txt'), 'r') as f:
            name = f.read()
        return MyObj(name=name)

    def save(self, my_obj: MyObj) -> None:
        """Write to artifact store."""
        with fileio.open(os.path.join(self.uri, 'data.txt'), 'w') as f:
            f.write(my_obj.name)
```

{% hint style="info" %}
Pro-tip: Use the ZenML `fileio` module to ensure your materialization logic works across artifact stores (local and remote like S3 buckets).
{% endhint %}

Now, ZenML can use this materializer to handle the outputs and inputs of your customs object. Edit the pipeline as follows to see this in action:

```python
my_first_step.configure(output_materializers=MyMaterializer)
first_pipeline()
```

{% hint style="info" %}
Due to the typing of the inputs and outputs and the `ASSOCIATED_TYPES` attribute of the materializer, you won't necessarily have to add `.configure(output_materializers=MyMaterializer)` to the step. It should automatically be detected. It doesn't hurt to be explicit though.
{% endhint %}

This will now work as expected and yield the following output:

```shell
Creating run for pipeline: `first_pipeline`
Cache enabled for pipeline `first_pipeline`
Using stack `default` to run pipeline `first_pipeline`...
Step `my_first_step` has started.
Step `my_first_step` has finished in 0.081s.
Step `my_second_step` has started.
The following object was passed to this step: `my_object`
Step `my_second_step` has finished in 0.048s.
Pipeline run `first_pipeline-22_Apr_22-10_58_51_135729` has finished in 0.153s.
```

<details>

<summary>Code Example for Materializing Custom Objects</summary>

```python
import logging
import os
from typing import Type

from zenml import step, pipeline

from zenml.enums import ArtifactType
from zenml.io import fileio
from zenml.materializers.base_materializer import BaseMaterializer


class MyObj:
    def __init__(self, name: str):
        self.name = name


class MyMaterializer(BaseMaterializer):
    ASSOCIATED_TYPES = (MyObj,)
    ASSOCIATED_ARTIFACT_TYPE = ArtifactType.DATA

    def load(self, data_type: Type[MyObj]) -> MyObj:
        """Read from artifact store."""
        with fileio.open(os.path.join(self.uri, 'data.txt'), 'r') as f:
            name = f.read()
        return MyObj(name=name)

    def save(self, my_obj: MyObj) -> None:
        """Write to artifact store."""
        with fileio.open(os.path.join(self.uri, 'data.txt'), 'w') as f:
            f.write(my_obj.name)


@step
def my_first_step() -> MyObj:
    """Step that returns an object of type MyObj."""
    return MyObj("my_object")


my_first_step.configure(output_materializers=MyMaterializer)


@step
def my_second_step(my_obj: MyObj) -> None:
    """Step that log the input object and returns nothing."""
    logging.info(
        f"The following object was passed to this step: `{my_obj.name}`"
    )


@pipeline
def first_pipeline():
    output_1 = my_first_step()
    my_second_step(output_1)


if __name__ == "__main__":
    first_pipeline()
```

</details>

## Skipping materialization

{% hint style="warning" %}
Skipping materialization might have unintended consequences for downstream tasks that rely on materialized artifacts. Only skip materialization if there is no other way to do what you want to do.
{% endhint %}

While materializers should in most cases be used to control how artifacts are returned and consumed from pipeline steps, you might sometimes need to have a completely unmaterialized artifact in a step, e.g., if you need to know the exact path to where your artifact is stored.

An unmaterialized artifact is a `zenml.materializers.UnmaterializedArtifact`. Among others, it has a property `uri` that points to the unique path in the artifact store where the artifact is persisted. One can use an unmaterialized artifact by specifying `UnmaterializedArtifact` as the type in the step:

```python
from zenml.materializers import UnmaterializedArtifact
from zenml import step


@step
def my_step(my_artifact: UnmaterializedArtifact):  # rather than pd.DataFrame
    pass
```

#### Example

The following shows an example of how unmaterialized artifacts can be used in the steps of a pipeline. The pipeline we define will look like this:

```shell
s1 -> s3 
s2 -> s4
```

`s1` and `s2` produce identical artifacts, however `s3` consumes materialized artifacts while `s4` consumes unmaterialized artifacts. `s4` can now use the `dict_.uri` and `list_.uri` paths directly rather than their materialized counterparts.

```python
from typing_extensions import Annotated  # or `from typing import Annotated on Python 3.9+
from typing import Dict, List, Tuple

from zenml.materializers import UnmaterializedArtifact
from zenml import pipeline, step


@step
def step_1() -> Tuple[
    Annotated[Dict[str, str], "dict_"],
    Annotated[List[str], "list_"],
]:
    return {"some": "data"}, []


@step
def step_2() -> Tuple[
    Annotated[Dict[str, str], "dict_"],
    Annotated[List[str], "list_"],
]:
    return {"some": "data"}, []


@step
def step_3(dict_: Dict, list_: List) -> None:
    assert isinstance(dict_, dict)
    assert isinstance(list_, list)


@step
def step_4(
        dict_: UnmaterializedArtifact,
        list_: UnmaterializedArtifact,
) -> None:
    print(dict_.uri)
    print(list_.uri)


@pipeline
def example_pipeline():
    step_3(*step_1())
    step_4(*step_2())


example_pipeline()
```

## Interaction with custom artifact stores

When creating a custom artifact store, you may encounter a situation where the default materializers do not function properly. Specifically, the `fileio.open` method used in these materializers may not be compatible with your custom store due to not being implemented properly.

In this case, you can create a modified version of the failing materializer by copying it and modifying it to copy the artifact to a local path, then opening it from there. For example, consider the following implementation of a custom [PandasMaterializer](https://github.com/zenml-io/zenml/blob/main/src/zenml/materializers/pandas\_materializer.py) that works with a custom artifact store. In this implementation, we copy the artifact to a local path because we want to use the `pandas.read_csv` method to read it. If we were to use the `fileio.open` method instead, we would not need to make this copy.

{% hint style="warning" %}
It is worth noting that copying the artifact to a local path may not always be necessary and can potentially be a performance bottleneck.
{% endhint %}

<details>

<summary>Pandas Materializer code example</summary>

```python
import os
from typing import Any, Type, Union

import pandas as pd

from zenml.enums import ArtifactType
from zenml.io import fileio
from zenml.logger import get_logger
from zenml.materializers.base_materializer import BaseMaterializer

logger = get_logger(__name__)
PARQUET_FILENAME = "df.parquet.gzip"
COMPRESSION_TYPE = "gzip"

CSV_FILENAME = "df.csv"


class PandasMaterializer(BaseMaterializer):
    """Materializer to read data to and from pandas."""

    ASSOCIATED_TYPES = (pd.DataFrame, pd.Series)
    ASSOCIATED_ARTIFACT_TYPE = ArtifactType.DATA

    def __init__(self, uri: str):
        """Define `self.data_path`.
        Args:
            uri: The URI where the artifact data is stored.
        """
        super().__init__(uri)
        try:
            import pyarrow  # type: ignore

            self.pyarrow_exists = True
        except ImportError:
            self.pyarrow_exists = False
            logger.warning(
                "By default, the `PandasMaterializer` stores data as a "
                "`.csv` file. If you want to store data more efficiently, "
                "you can install `pyarrow` by running "
                "'`pip install pyarrow`'. This will allow `PandasMaterializer` "
                "to automatically store the data as a `.parquet` file instead."
            )
        finally:
            self.parquet_path = os.path.join(self.uri, PARQUET_FILENAME)
            self.csv_path = os.path.join(self.uri, CSV_FILENAME)

    def load(self, data_type: Type[Any]) -> Union[pd.DataFrame, pd.Series]:
        """Reads `pd.DataFrame` or `pd.Series` from a `.parquet` or `.csv` file.
        Args:
            data_type: The type of the data to read.
        Raises:
            ImportError: If pyarrow or fastparquet is not installed.
        Returns:
            The pandas dataframe or series.
        """
        temp_dir = tempfile.mkdtemp(prefix="zenml-temp-")
        if fileio.exists(self.parquet_path):
            if self.pyarrow_exists:
                # Create a temporary file
                temp_file = os.path.join(str(temp_dir), PARQUET_FILENAME)
                # Copy the data to the temporary file
                fileio.copy(self.parquet_path, temp_file)
                # Load the data from the temporary file
                df = pd.read_parquet(temp_file)
            else:
                raise ImportError(
                    "You have an old version of a `PandasMaterializer` "
                    "data artifact stored in the artifact store "
                    "as a `.parquet` file, which requires `pyarrow` "
                    "for reading, You can install `pyarrow` by running "
                    "'`pip install pyarrow fastparquet`'."
                )
        else:
            # Create a temporary file
            temp_file = os.path.join(str(temp_dir), CSV_FILENAME)
            # Copy the data to the temporary file
            fileio.copy(self.csv_path, temp_file)
            # Load the data from the temporary file
            df = pd.read_csv(temp_file, index_col=0, parse_dates=True)

        # Cleanup and return
        fileio.rmtree(temp_dir)

        # validate the type of the data.
        def is_dataframe_or_series(
                df: Union[pd.DataFrame, pd.Series]
        ) -> Union[pd.DataFrame, pd.Series]:
            """Checks if the data is a `pd.DataFrame` or `pd.Series`.
            Args:
                df: The data to check.
            Returns:
                The data if it is a `pd.DataFrame` or `pd.Series`.
            """
            if issubclass(data_type, pd.Series):
                # Taking the first column if it's a series as the assumption
                # is that there will only be one
                assert len(df.columns) == 1
                df = df[df.columns[0]]
                return df
            else:
                return df

        return is_dataframe_or_series(df)

    def save(self, df: Union[pd.DataFrame, pd.Series]) -> None:
        """Writes a pandas dataframe or series to the specified filename.
        Args:
            df: The pandas dataframe or series to write.
        """
        if isinstance(df, pd.Series):
            df = df.to_frame(name="series")

        # Create a temporary file to store the data
        if self.pyarrow_exists:
            with tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".gzip", delete=False
            ) as f:
                df.to_parquet(f.name, compression=COMPRESSION_TYPE)
                fileio.copy(f.name, self.parquet_path)
        else:
            with tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".csv", delete=False
            ) as f:
                df.to_csv(f.name, index=True)
                fileio.copy(f.name, self.csv_path)

        # Close and remove the temporary file
        fileio.remove(f.name)

```

</details>

<!-- For scarf -->
<figure><img alt="ZenML Scarf" referrerpolicy="no-referrer-when-downgrade" src="https://static.scarf.sh/a.png?x-pxid=f0b4f458-0a54-4fcd-aa95-d5ee424815bc" /></figure>

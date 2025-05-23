import atheris
import sys
import os
import tempfile
from configparser import ParsingError
from utils import (
    setup_git_environment,
    handle_exception,
    get_max_filename_length,
)

# Setup the Git environment
setup_git_environment()
from git import Repo, GitCommandError, InvalidGitRepositoryError


def sanitize_input(input_str, max_length=255):
    """Sanitize and truncate inputs to avoid invalid Git operations."""
    sanitized = "".join(ch for ch in input_str if ch.isalnum() or ch in ("-", "_", "."))
    return sanitized[:max_length]


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    with tempfile.TemporaryDirectory() as repo_temp_dir:
        repo = Repo.init(path=repo_temp_dir)
        repo.index.commit("Initial commit")

        try:
            with tempfile.TemporaryDirectory() as submodule_temp_dir:
                sub_repo = Repo.init(submodule_temp_dir, bare=fdp.ConsumeBool())
                commit_message = sanitize_input(fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 512)))
                sub_repo.index.commit(commit_message)

                submodule_name = sanitize_input(
                    fdp.ConsumeUnicodeNoSurrogates(
                        fdp.ConsumeIntInRange(1, get_max_filename_length(repo.working_tree_dir))
                    )
                )

                submodule_path = os.path.relpath(
                    os.path.join(repo.working_tree_dir, submodule_name),
                    start=repo.working_tree_dir,
                )

                # Ensure submodule_path is valid
                if not submodule_name or submodule_name.startswith("/") or ".." in submodule_name:
                    return -1  # Reject invalid input so they are not added to the corpus

                submodule = repo.create_submodule(submodule_name, submodule_path, url=sub_repo.git_dir)
                repo.index.commit("Added submodule")

                with submodule.config_writer() as writer:
                    key_length = fdp.ConsumeIntInRange(1, max(1, fdp.remaining_bytes()))
                    value_length = fdp.ConsumeIntInRange(1, max(1, fdp.remaining_bytes()))

                    writer.set_value(
                        sanitize_input(fdp.ConsumeUnicodeNoSurrogates(key_length)),
                        sanitize_input(fdp.ConsumeUnicodeNoSurrogates(value_length)),
                    )
                    writer.release()

                submodule.update(
                    init=fdp.ConsumeBool(),
                    dry_run=fdp.ConsumeBool(),
                    force=fdp.ConsumeBool(),
                )

                submodule_repo = submodule.module()

                new_file_name = sanitize_input(
                    fdp.ConsumeUnicodeNoSurrogates(
                        fdp.ConsumeIntInRange(1, get_max_filename_length(submodule_repo.working_tree_dir))
                    )
                )
                new_file_path = os.path.join(submodule_repo.working_tree_dir, new_file_name)
                with open(new_file_path, "wb") as new_file:
                    new_file.write(fdp.ConsumeBytes(fdp.ConsumeIntInRange(1, 512)))

                submodule_repo.index.add([new_file_path])
                submodule_repo.index.commit("Added new file to submodule")

                repo.submodule_update(recursive=fdp.ConsumeBool())
                submodule_repo.head.reset(
                    commit="HEAD~1",
                    working_tree=fdp.ConsumeBool(),
                    head=fdp.ConsumeBool(),
                )

                module_option_value, configuration_option_value = fdp.PickValueInList(
                    [(True, False), (False, True), (True, True)]
                )
                submodule.remove(
                    module=module_option_value,
                    configuration=configuration_option_value,
                    dry_run=fdp.ConsumeBool(),
                    force=fdp.ConsumeBool(),
                )
                repo.index.commit(f"Removed submodule {submodule_name}")

        except (
            ParsingError,
            GitCommandError,
            InvalidGitRepositoryError,
            FileNotFoundError,
            FileExistsError,
            IsADirectoryError,
            NotADirectoryError,
            BrokenPipeError,
            PermissionError,
        ):
            return -1
        except Exception as e:
            return handle_exception(e)


def main():
    atheris.instrument_all()
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()

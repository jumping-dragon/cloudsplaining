"""
Scan a single policy file to identify missing resource constraints.
"""
# Copyright (c) 2020, salesforce.com, inc.
# All rights reserved.
# Licensed under the BSD 3-Clause license.
# For full license text, see the LICENSE file in the repo root
# or https://opensource.org/licenses/BSD-3-Clause
import sys
import logging
import json
from pathlib import Path
import yaml
import click
import click_log
from cloudsplaining.output.findings import Findings, PolicyFinding
from cloudsplaining.shared.constants import EXCLUSIONS_FILE
from cloudsplaining.scan.policy_document import PolicyDocument
from cloudsplaining.shared.exclusions import (
    Exclusions,
    DEFAULT_EXCLUSIONS,
)

logger = logging.getLogger(__name__)
click_log.basic_config(logger)
BOLD = "\033[1m"
RED = "\033[91m"
END = "\033[0m"


@click.command(
    short_help="Scan a single policy file to identify identify missing resource constraints."
)
@click.option(
    "--input-file",
    type=str,
    # required=True,
    help="Path of the IAM policy file to evaluate.",
)
@click.option(
    "--exclusions-file",
    help="A yaml file containing a list of actions to ignore when scanning.",
    type=click.Path(exists=True),
    required=False,
    default=EXCLUSIONS_FILE,
)
@click.option(
    "--high-priority-only",
    required=False,
    default=False,
    is_flag=True,
    help="If issues are found, only print the high priority risks"
    " (Resource Exposure, Privilege Escalation, Data Exfiltration). This can help with prioritization.",
)
@click_log.simple_verbosity_option(logger)
# pylint: disable=redefined-builtin
def scan_policy_file(input_file, exclusions_file, high_priority_only):  # pragma: no cover
    """Scan a single policy file to identify missing resource constraints."""
    if input_file:
        # Get the Policy
        with open(input_file) as json_file:
            logger.debug(f"Opening {input_file}")
            policy = json.load(json_file)
        policy_name = Path(input_file).stem
    else:
        try:
            policy = json.load(sys.stdin)
        except json.decoder.JSONDecodeError as j_e:
            logger.critical(j_e)
            sys.exit()
        policy_name = "StdinPolicy"

    # Get the exclusions configuration
    with open(exclusions_file, "r") as yaml_file:
        try:
            exclusions_cfg = yaml.safe_load(yaml_file)
        except yaml.YAMLError as exc:
            logger.critical(exc)
    exclusions = Exclusions(exclusions_cfg)

    # Run the scan and get the raw data.
    results = scan_policy(policy, policy_name, exclusions)

    # There will only be one finding in the results but it is in a list.
    results_exist = 0
    if results:
        if results.get("PrivilegeEscalation"):
            print(f"{RED}Potential Issue found: Policy is capable of Privilege Escalation{END}")
            results_exist += 1
            for item in results.get("PrivilegeEscalation"):
                print(f"- Method: {item.get('type')}")
                print(f"  Actions: {', '.join(item.get('PrivilegeEscalation'))}\n")
        if results.get("DataExfiltrationActions"):
            results_exist += 1
            print(f"{RED}Potential Issue found: Policy is capable of Data Exfiltration{END}")
            print(
                f"{BOLD}Actions{END}: {', '.join(results.get('DataExfiltrationActions'))}\n"
            )
        if results.get("PermissionsManagementActions"):
            results_exist += 1
            print(f"{RED}Potential Issue found: Policy is capable of Resource Exposure{END}")
            print(
                f"{BOLD}Actions{END}: {', '.join(results.get('PermissionsManagementActions'))}\n"
            )
        if not high_priority_only:
            results_exist += 1
            print(f"{RED}Potential Issue found: Policy is capable of Unrestricted Infrastructure Modification{END}")
            print(f"{BOLD}Actions{END}: {', '.join(results.get('Actions'))}")
        if results_exist == 0:
            print("There were no results found.")
    else:
        print("There were no results found.")


def scan_policy(policy_json, policy_name, exclusions=DEFAULT_EXCLUSIONS):
    """
    Scan a policy document for missing resource constraints.

    :param exclusions: Exclusions object
    :param policy_json: The AWS IAM policy document.
    :param policy_name: The name of the IAM policy. Defaults to the filename when used from command line.
    :return:
    """
    actions_missing_resource_constraints = []

    policy_document = PolicyDocument(policy_json)

    findings = Findings(exclusions)

    for statement in policy_document.statements:
        logger.debug("Evaluating statement: %s", statement.json)
        if statement.effect == "Allow":
            actions_missing_resource_constraints.extend(
                statement.missing_resource_constraints_for_modify_actions(exclusions)
            )
    if actions_missing_resource_constraints:
        these_results = list(
            dict.fromkeys(actions_missing_resource_constraints)
        )  # remove duplicates
        these_results.sort()
        finding = PolicyFinding(
            policy_name=policy_name,
            arn=policy_name,
            actions=these_results,
            policy_document=policy_document,
            exclusions=exclusions,
        )
        findings.add_policy_finding(finding)
        findings.single_use = True
        return finding.json
    else:
        return {}

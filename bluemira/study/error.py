# SPDX-FileCopyrightText: 2021-present M. Coleman, J. Cook, F. Franza
# SPDX-FileCopyrightText: 2021-present I.A. Maione, S. McIntosh
# SPDX-FileCopyrightText: 2021-present J. Morris, D. Short
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Error classes for the bluemira study and parametric scan subsystem.
"""

from bluemira.base.error import BluemiraError


class ScanError(BluemiraError):
    """
    Base exception class for parametric scans and design studies.
    """


class ScanExecutionError(ScanError):
    """
    Raised when an error occurs during build function execution in a scan.
    """


class ScanConstraintError(ScanError):
    """
    Raised when constraint evaluation fails or cannot be computed.
    """

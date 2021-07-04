{ stdenv, python3Packages }:

with python3Packages;

buildPythonApplication rec {
  pname = "power-monitor";
  version = "1.0.0";
  src = ./.;

  propagatedBuildInputs = [ requests
                            spidev
                            influxdb
                            prettytable
                            # remove: big closure
                            plotly
                          ];
}

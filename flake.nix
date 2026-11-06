{
  description = "X-Capture — screenshot tool for Linux";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      py = pkgs.python3.withPackages (p: [ p.pyqt6 p.xlib ]);
    in {
      packages.${system}.default = pkgs.stdenv.mkDerivation {
        pname = "x-capture";
        version = "1.2.0";
        src = ./.;
        nativeBuildInputs = [ pkgs.makeWrapper ];
        installPhase = ''
          mkdir -p $out/share/x-capture $out/bin $out/share/applications $out/share/icons/hicolor/scalable/apps
          cp -r xcapture $out/share/x-capture/
          cp data/x-capture.desktop $out/share/applications/
          cp data/x-capture.svg $out/share/icons/hicolor/scalable/apps/
          makeWrapper ${py}/bin/python3 $out/bin/x-capture \
            --prefix PYTHONPATH : $out/share/x-capture \
            --set XCAPTURE_EXE $out/bin/x-capture \
            --add-flags "-m xcapture"
        '';
      };
      apps.${system}.default = {
        type = "app";
        program = "${self.packages.${system}.default}/bin/x-capture";
      };
    };
}

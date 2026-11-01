/* Kuyumcu Veresiye Premium — küçük arayüz yardımcıları (harici bağımlılık yok) */
(function () {
  "use strict";

  /* ---------------------------------------------------------- menü ------ */
  document.addEventListener("click", function (e) {
    var tus = e.target.closest("[data-menu]");
    if (tus) {
      document.body.classList.toggle("menu-acik");
      return;
    }
    if (document.body.classList.contains("menu-acik") &&
        !e.target.closest(".sidebar") && !e.target.closest("[data-menu]")) {
      document.body.classList.remove("menu-acik");
    }
    var kapat = e.target.closest(".mesaj .kapat");
    if (kapat) kapat.closest(".mesaj").remove();
  });

  /* ------------------------------------------------------- uyarı kapatma - */
  setTimeout(function () {
    document.querySelectorAll(".mesaj.basari, .mesaj.bilgi").forEach(function (m) {
      m.style.transition = "opacity .4s";
      m.style.opacity = "0";
      setTimeout(function () { m.remove(); }, 420);
    });
  }, 5000);

  /* ------------------------------------------------------- onay diyalogu  */
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.hasAttribute("data-onay")) {
      if (!window.confirm(form.getAttribute("data-onay"))) {
        e.preventDefault();
        return;
      }
    }
    if (form.hasAttribute("data-sebep")) {
      var varsayilan = form.getAttribute("data-sebep") || "İptal edildi.";
      var sebep = window.prompt(form.getAttribute("data-sebep-metin") ||
                                "İptal sebebi yazın:", varsayilan);
      if (sebep === null) { e.preventDefault(); return; }
      if (!sebep.trim()) sebep = varsayilan;
      var alan = form.querySelector("input[name=sebep]");
      if (!alan) {
        alan = document.createElement("input");
        alan.type = "hidden";
        alan.name = "sebep";
        form.appendChild(alan);
      }
      alan.value = sebep;
    }
  });

  /* ------------------------------------------------------- canlı arama ---- */
  document.addEventListener("input", function (e) {
    var kutu = e.target.closest("[data-ara]");
    if (!kutu) return;
    var hedef = document.querySelector(kutu.getAttribute("data-ara"));
    if (!hedef) return;
    var q = kutu.value.trim().toLocaleLowerCase("tr");
    hedef.querySelectorAll("tbody tr").forEach(function (tr) {
      var metin = (tr.getAttribute("data-ara-metin") || tr.textContent)
        .toLocaleLowerCase("tr");
      tr.style.display = !q || metin.indexOf(q) !== -1 ? "" : "none";
    });
  });

  /* ------------------------------------------------------- bugün tarihi --- */
  var bugun = new Date().toISOString().slice(0, 10);
  document.querySelectorAll("input[data-bugun]").forEach(function (i) {
    if (!i.value) i.value = bugun;
  });

  /* ------------------------------------------- tahsilat çevrim önizlemesi - */
  function sayi(metin) {
    if (!metin) return NaN;
    var m = String(metin).trim().replace(/\s/g, "").replace(/₺/g, "")
      .replace(/gr/gi, "").replace(/TL/gi, "");
    if (!m) return NaN;
    if (m.indexOf(",") > -1 && m.indexOf(".") > -1) {
      m = m.lastIndexOf(",") > m.lastIndexOf(".")
        ? m.replace(/\./g, "").replace(",", ".")
        : m.replace(/,/g, "");
    } else if (m.indexOf(",") > -1) {
      m = m.replace(",", ".");
    }
    return parseFloat(m);
  }

  function bicim(v) {
    return v.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  document.addEventListener("input", function (e) {
    var form = e.target.closest("[data-cevir-ozet]");
    if (!form) return;
    var tutar = sayi(form.querySelector("[name=tutar]").value);
    var pb = form.querySelector("[name=pb]").value;
    var hedef = form.querySelector("[name=hedef]").value;
    var kurAlani = form.querySelector("[name=kur]");
    var kur = kurAlani ? sayi(kurAlani.value) : 0;
    var kutu = form.querySelector("[data-cevir-sonuc]");
    if (!kutu) return;
    if (isNaN(tutar) || tutar <= 0) {
      kutu.textContent = "Ödemeyi yazın — uygulanacak borç miktarı burada görünecek.";
      return;
    }
    if (pb === hedef) {
      kutu.textContent = "Uygulanacak: " +
        (pb === "tl" ? bicim(tutar) + " ₺ TL borcu" :
         tutar.toLocaleString("tr-TR", { maximumFractionDigits: 3 }) + " gr altın borcu");
      return;
    }
    if (!kur || kur <= 0) {
      kutu.textContent = "Çevrim için güncel gram fiyat gerekli (kırmızı uyarı görünürse " +
        "Ayarlar'dan fiyatı güncelleyin).";
      return;
    }
    var miktar = pb === "tl" ? tutar / kur : tutar * kur;
    var metin = pb === "tl"
      ? bicim(tutar) + " ₺ → gram fiyat " + bicim(kur) + " ₺/gr ile " +
        miktar.toLocaleString("tr-TR", { maximumFractionDigits: 3 }) + " gr altın borcundan düşülecek"
      : tutar.toLocaleString("tr-TR", { maximumFractionDigits: 3 }) + " gr → gram fiyat " +
        bicim(kur) + " ₺/gr ile " + bicim(miktar) + " ₺ TL borcundan düşülecek";
    kutu.textContent = metin;
  });

  /* ------------------------------------------- ürün seçici otomatik doldur - */
  document.addEventListener("change", function (e) {
    var secici = e.target.closest("[data-urun-secici]");
    if (!secici) return;
    var form = secici.closest("form");
    if (!form) return;
    var opt = secici.selectedOptions[0];
    if (!opt || secici.value === "0") return;
    var tutarAlani = form.querySelector("[name=tutar]");
    var pbAlani = form.querySelector("[name=pb]");
    var aciklamaAlani = form.querySelector("[name=aciklama]");
    if (!tutarAlani) return;
    var pb = pbAlani ? pbAlani.value : "tl";
    var miktar = pb === "altin" ? parseFloat(opt.getAttribute("data-gr") || "0")
                                : parseFloat(opt.getAttribute("data-tl") || "0");
    if (miktar > 0) {
      tutarAlani.value = miktar.toLocaleString("tr-TR",
        pb === "altin"
          ? { maximumFractionDigits: 3 }
          : { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      tutarAlani.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (aciklamaAlani && !aciklamaAlani.value.trim()) {
      var ad = opt.getAttribute("data-ad") || "";
      var birim = opt.getAttribute("data-birim") || "adet";
      aciklamaAlani.value = pb === "altin"
        ? ad + " — " + miktar.toLocaleString("tr-TR", { maximumFractionDigits: 3 }) + " " + birim
        : ad;
      aciklamaAlani.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  /* ------------------------------------------------------- yazdırma ------- */
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-yazdir]")) window.print();
  });

  /* ---------------------------------------------- formlar hep açık beyaslı */
  /* kullanım kolaylığı: kayıt formları sayfada hep görünür
     (listeye kaydırma: ":kayit" hedefine oturulur). */
  document.querySelectorAll("details.acilir").forEach(function (d) {
    if (!d.hasAttribute("data-kapali")) d.setAttribute("open", "");
  });
})();

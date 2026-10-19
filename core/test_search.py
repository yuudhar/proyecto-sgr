import re

from django.test import SimpleTestCase
from django.urls import reverse

from core.crud import PAGE_SIZE
from core.search import MAX_WORD_LENGTH, number_like, word_pattern
from core.testing import PortalTestCase
from organization.models import Beneficiary


class WordPatternTests(SimpleTestCase):
    def matches(self, word, text):
        return re.search(word_pattern(word), text, re.IGNORECASE) is not None

    def test_accents_and_case_do_not_matter(self):
        self.assertTrue(self.matches("nunez", "Núñez"))
        self.assertTrue(self.matches("Núñez", "nunez"))
        self.assertTrue(self.matches("JOSE", "José"))
        self.assertTrue(self.matches("jose", "JOSÉ"))
        self.assertTrue(self.matches("munoz", "Carla Muñoz"))
        self.assertFalse(self.matches("nunes", "Núñez"))

    def test_special_characters_are_searched_literally(self):
        for word in ("a.b", "(x)", "[a", "a+b", "a*", "\\", "a|b", "$5", "^a", "{1}", "a?"):
            re.compile(word_pattern(word))
            self.assertTrue(self.matches(word, f"zz {word} zz"), word)
        self.assertFalse(self.matches("a.b", "axb"))

    def test_a_rut_is_found_with_or_without_dots_and_dash(self):
        stored = "11111111-1"
        for written in ("11.111.111-1", "11111111-1", "111111111", "11.111.111", "11111111", "11.111", "1111"):
            self.assertTrue(self.matches(written, stored), written)
        self.assertTrue(self.matches("11111111", "11.111.111-1"))
        self.assertFalse(self.matches("11.111.112", stored))

    def test_a_rut_ending_in_k_is_found(self):
        self.assertTrue(self.matches("10.000.013-k", "10000013-K"))
        self.assertTrue(self.matches("10000013-K", "10.000.013-k"))
        self.assertFalse(self.matches("10.000.013-1", "10000013-K"))

    def test_a_phone_is_found_with_or_without_spaces(self):
        self.assertTrue(self.matches("56911111111", "+56 9 1111 1111"))
        self.assertTrue(self.matches("+56 9 1111 1111".replace(" ", ""), "+56911111111"))
        self.assertTrue(self.matches("91111", "+56 9 1111 1111"))

    def test_only_numbers_with_three_digits_or_more_ignore_separators(self):
        self.assertEqual(number_like("11.111.111-1"), "111111111")
        self.assertEqual(number_like("10.000.013-k"), "10000013k")
        self.assertEqual(number_like("123"), "123")
        self.assertEqual(number_like("12"), "")
        self.assertEqual(number_like("a1b"), "")
        self.assertEqual(number_like("EVD-0001"), "")

    def test_a_code_with_letters_is_searched_as_written(self):
        self.assertTrue(self.matches("EVD-NORTE-0001", "evd-norte-0001"))
        self.assertFalse(self.matches("EVD-NORTE-0001", "EVD-NORTE-0002"))

    def test_very_long_words_are_cut(self):
        self.assertEqual(word_pattern("x" * 500), word_pattern("x" * MAX_WORD_LENGTH))


class ListSearchTests(PortalTestCase):
    def found(self, path, query, attribute="contact_name", **params):
        response = self.client.get(path, {"q": query, **params})
        self.assertEqual(response.status_code, 200)
        return [getattr(row.obj, attribute) for row in response.context["rows"]]

    def test_search_ignores_accents_and_case(self):
        self.login_as("admin")
        for query in ("munoz", "MUÑOZ", "Muñoz", "muñoz"):
            self.assertEqual(self.found(reverse("core:atencion"), query), ["Carla Muñoz"], query)

    def test_search_finds_a_rut_however_it_is_written(self):
        self.login_as("admin")
        for query in ("11.111.111-1", "11111111-1", "111111111", "11111111"):
            self.assertEqual(self.found(reverse("core:atencion"), query), ["María Pérez"], query)

    def test_search_finds_a_phone_with_or_without_the_plus(self):
        self.login_as("admin")
        for query in ("+56911111111", "56911111111", "911111111"):
            self.assertEqual(self.found(reverse("core:atencion"), query), ["María Pérez"], query)

    def test_every_word_must_match(self):
        self.login_as("admin")
        url = reverse("core:atencion")
        self.assertEqual(self.found(url, "maria perez"), ["María Pérez"])
        self.assertEqual(self.found(url, "perez 11111111"), ["María Pérez"])
        self.assertEqual(self.found(url, "maria soto"), [])

    def test_search_can_reach_archived_records_on_request(self):
        self.login_as("admin")
        url = reverse("core:atencion")
        self.assertEqual(self.found(url, "22.222.222-2"), [])
        self.assertEqual(self.found(url, "22.222.222-2", archivados="1"), ["Juan Soto"])

    def test_search_never_reaches_other_delegations(self):
        self.login_as("matias.cavieres")
        url = reverse("core:atencion")
        self.assertEqual(self.found(url, "33.333.333-3"), [])
        self.assertEqual(self.found(url, "11.111.111-1"), ["María Pérez"])

    def test_odd_texts_do_not_break_the_search(self):
        self.login_as("admin")
        url = reverse("core:atencion")
        for query in ("(", "[", "\\", "a|b", "*", "%", "_", "'; DROP TABLE x; --", "<script>", "x" * 300):
            response = self.client.get(url, {"q": query})
            self.assertEqual(response.status_code, 200, query)

    def test_users_are_searched_by_profile_and_delegation(self):
        self.login_as("admin")
        url = reverse("core:usuarios_list")
        self.assertEqual(self.found(url, "coordinación", "username"), ["coordinacion1"])
        self.assertEqual(self.found(url, "coordinacion", "username"), ["coordinacion1"])
        self.assertEqual(self.found(url, "delegación sur", "username"), ["matias.quiroz"])
        self.assertEqual(set(self.found(url, "verificador", "username")), {"matias.cavieres", "matias.quiroz"})

    def test_a_user_with_several_profiles_is_listed_once(self):
        self.login_as("admin")
        usernames = self.found(reverse("core:usuarios_list"), "o", "username")
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertIn("matias.cavieres", usernames)


class PagerTests(PortalTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Beneficiary.objects.bulk_create(
            [Beneficiary(rut=f"9{number:07d}-1", name=f"Persona Número {number:02d}") for number in range(45)]
        )

    def test_lists_show_one_page_at_a_time(self):
        self.login_as("admin")
        total = Beneficiary.objects.count()
        url = reverse("core:beneficiarios_list")
        response = self.client.get(url)
        self.assertEqual(len(response.context["rows"]), PAGE_SIZE)
        self.assertEqual(response.context["page"].paginator.count, total)
        self.assertContains(response, f"Mostrando 1–{PAGE_SIZE} de {total}")
        last = self.client.get(url, {"page": 3})
        self.assertEqual(len(last.context["rows"]), total - 2 * PAGE_SIZE)

    def test_a_page_out_of_range_shows_the_last_one(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"), {"page": 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].number, response.context["page"].paginator.num_pages)
        response = self.client.get(reverse("core:beneficiarios_list"), {"page": "abc"})
        self.assertEqual(response.context["page"].number, 1)

    def test_page_links_keep_the_search(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"), {"q": "persona"})
        self.assertContains(response, "q=persona&amp;page=2")

    def test_small_results_have_no_pager(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:beneficiarios_list"), {"q": "Número 07"})
        self.assertEqual(len(response.context["rows"]), 1)
        self.assertNotContains(response, "Páginas del listado")

    def test_the_sort_order_applies_to_the_whole_result_not_just_the_page(self):
        self.login_as("admin")
        url = reverse("core:beneficiarios_list")
        first = self.client.get(url, {"orden": "name", "dir": "asc"}).context["rows"][0].obj.name
        last_page = self.client.get(url, {"orden": "name", "dir": "desc", "page": 1}).context["rows"][0].obj.name
        self.assertEqual(first, Beneficiary.objects.order_by("name").first().name)
        self.assertEqual(last_page, Beneficiary.objects.order_by("-name").first().name)
